import abc
import logging
from enum import Enum
from typing import Any, Literal, Optional, Sequence, Type, Union, cast

from pydantic import BaseModel, ConfigDict, model_validator
from telebot import types as tg
from telebot_components.form.field import (
    FormField,
    FormFieldResultFormattingOpts,
    PlainTextField,
    SingleSelectField,
)
from telebot_components.form.form import Form as ComponentsForm
from telebot_components.form.form import FormBranch
from telebot_components.form.handler import FormExitContext as ComponentsFormExitContext
from telebot_components.form.handler import FormHandler as ComponentsFormHandler
from telebot_components.form.handler import (
    FormHandlerConfig as ComponentsFormHandlerConfig,
)
from telebot_components.utils import emoji_hash
from typing_extensions import Self

from telebot_constructor.user_flow.blocks.base import UserFlowBlock
from telebot_constructor.user_flow.blocks.constants import (
    FORM_CANCEL_CMD,
    FORM_SKIP_FIELD_CMD,
)
from telebot_constructor.user_flow.types import (
    SetupResult,
    UserFlowBlockId,
    UserFlowContext,
    UserFlowSetupContext,
)
from telebot_constructor.utils import AnyChatId, telegram_user_link, without_nones
from telebot_constructor.utils.pydantic import (
    ExactlyOneNonNullFieldModel,
    LocalizableText,
    MultilangText,
)

logger = logging.getLogger(__name__)

# region: form fields


class BaseFormFieldConfig(BaseModel, abc.ABC):
    id: str
    name: str
    prompt: LocalizableText
    is_required: bool
    result_formatting: Union[FormFieldResultFormattingOpts, Literal["auto"], None]

    def auto_result_formatting_opts(self) -> FormFieldResultFormattingOpts:
        return FormFieldResultFormattingOpts(
            descr=self.name,
            is_multiline=False,
        )

    def base_field_kwargs(self) -> dict[str, Any]:
        if isinstance(self.result_formatting, FormFieldResultFormattingOpts):
            result_formatting_opts = self.result_formatting
        elif self.result_formatting == "auto":
            result_formatting_opts = self.auto_result_formatting_opts()
        else:
            result_formatting_opts = None

        # common kwargs in FormField
        return dict(
            name=self.id,
            required=self.is_required,
            query_message=self.prompt,
            result_formatting_opts=result_formatting_opts,
        )

    @abc.abstractmethod
    def construct_field(self) -> FormField: ...


class PlainTextFormFieldConfig(BaseFormFieldConfig):
    is_long_text: bool
    empty_text_error_msg: LocalizableText

    def auto_result_formatting_opts(self) -> FormFieldResultFormattingOpts:
        return FormFieldResultFormattingOpts(
            descr=self.name,
            is_multiline=self.is_long_text,
        )

    def construct_field(self) -> PlainTextField:
        return PlainTextField(
            empty_text_error_msg=self.empty_text_error_msg,
            **self.base_field_kwargs(),
        )


class EnumOption(BaseModel):
    id: str
    label: LocalizableText


class SingleSelectFormFieldConfig(BaseFormFieldConfig):
    options: list[EnumOption]
    invalid_enum_error_msg: LocalizableText

    def construct_field(self) -> SingleSelectField:
        # HACK: we need to programmatically create Enum class from a user-provided set of options
        # see https://docs.python.org/3/howto/enum.html#functional-api
        # but also, we need to inject this class into global scope so that (de)serializers can find this class
        # in the present module
        # so we do this using globals()
        enum_def = [(o.id, o.label) for o in self.options]
        enum_class_name = f"{self.id}_single_select_field_options"
        EnumClass: Type[Enum] = Enum(enum_class_name, enum_def, module=__name__)  # type: ignore
        globals()[enum_class_name] = EnumClass
        return SingleSelectField(
            EnumClass=EnumClass,
            invalid_enum_value_error_msg=self.invalid_enum_error_msg,
            **self.base_field_kwargs(),  # type: ignore
        )


class FormFieldConfig(ExactlyOneNonNullFieldModel):
    plain_text: Optional[PlainTextFormFieldConfig] = None
    single_select: Optional[SingleSelectFormFieldConfig] = None

    def specific_config(self) -> BaseFormFieldConfig:
        return self.plain_text or self.single_select  # type: ignore


# endregion


class FormBranchConfig(ExactlyOneNonNullFieldModel):
    members: list["BranchingFormMemberConfig"]
    condition_match_value: Optional[str] = None

    def constuct_branch(self) -> FormBranch:
        return FormBranch(
            members=[m.construct_member() for m in self.members],
            condition=self.condition_match_value,  # type: ignore
        )


class BranchingFormMemberConfig(ExactlyOneNonNullFieldModel):
    field: Optional[FormFieldConfig] = None
    branch: Optional[FormBranchConfig] = None

    def construct_member(self) -> Union[FormField, FormBranch]:
        if self.field is not None:
            return self.field.specific_config().construct_field()
        elif self.branch is not None:
            return self.branch.constuct_branch()
        else:
            raise RuntimeError("All fields in exactly one non null field model are None")


class FormMessages(BaseModel):
    form_start: LocalizableText
    cancel_command_is: LocalizableText
    field_is_skippable: LocalizableText
    field_is_not_skippable: LocalizableText
    please_enter_correct_value: LocalizableText
    unsupported_command: LocalizableText

    # for easier frontend validation
    model_config = ConfigDict(extra="forbid")


class FormResultsExportToChatConfig(BaseModel):
    chat_id: AnyChatId
    via_feedback_handler: bool


class FormResultUserAttribution(Enum):
    NONE = "none"  # no data collected from user
    UNIQUE_ID = "unique_id"  # only a unique anonymized ID
    NAME = "name"  # only telegram name
    FULL = "full"  # telegram name, username, user id


class FormResultsExport(BaseModel):
    user_attribution: FormResultUserAttribution = FormResultUserAttribution.NONE
    echo_to_user: bool
    to_chat: Optional[FormResultsExportToChatConfig]

    is_anonymous: Optional[bool] = None  # deprecated, use user_attribution instead

    @model_validator(mode="after")
    def backwards_compatibility(self) -> Self:
        if self.is_anonymous is None and self.user_attribution is None:
            raise ValueError("At least one of the properties must not be None: is_anonymous, user_attribution")
        if self.is_anonymous is not None:
            self.user_attribution = (
                FormResultUserAttribution.NONE if self.is_anonymous else FormResultUserAttribution.FULL
            )
        self.is_anonymous = None
        return self


class FormBlock(UserFlowBlock):
    """
    Block with a series of questions to user with options to export their answers in various formats
    """

    form_name: str
    members: list[BranchingFormMemberConfig]
    messages: FormMessages
    results_export: FormResultsExport

    form_completed_next_block_id: Optional[UserFlowBlockId]
    form_cancelled_next_block_id: Optional[UserFlowBlockId]

    def possible_next_block_ids(self) -> list[str]:
        return without_nones([self.form_cancelled_next_block_id, self.form_completed_next_block_id])

    def model_post_init(self, __context: Any) -> None:
        if not self.members:
            raise ValueError("Form must contain at least one member field")

    async def setup(self, context: UserFlowSetupContext) -> SetupResult:
        component_form_members: list[Union[FormField, FormBranch]] = [m.construct_member() for m in self.members]
        self._form = ComponentsForm.branching(component_form_members)

        cancelling_because_of_error_eng = "Something went wrong, details: {}"
        if context.language_store is not None:
            cancelling_because_of_error: LocalizableText = {
                lang: cancelling_because_of_error_eng for lang in context.language_store.languages
            }
        else:
            cancelling_because_of_error = cancelling_because_of_error_eng

        #                                          VVV impossible to generate type anntation for
        #                                              form result type, so we use Any
        self._form_handler = ComponentsFormHandler[Any](
            redis=context.redis,
            bot_prefix=context.bot_prefix,
            name=self.form_name,
            form=self._form,
            config=ComponentsFormHandlerConfig(
                echo_filled_field=False,
                form_starting_template=join_localizable_texts(
                    [
                        self.messages.form_start,
                        self.messages.cancel_command_is,
                    ],
                    sep="\n\n",
                ),
                can_skip_field_template=self.messages.field_is_skippable,
                cant_skip_field_msg=self.messages.field_is_not_skippable,
                retry_field_msg=self.messages.please_enter_correct_value,
                unsupported_cmd_error_template=self.messages.unsupported_command,
                cancelling_because_of_error_template=cancelling_because_of_error,
                cancel_cmd=FORM_CANCEL_CMD,
                skip_cmd=FORM_SKIP_FIELD_CMD,
            ),
            language_store=context.language_store,
        )

        def _user_flow_context_for_next_block(form_exit_context: ComponentsFormExitContext) -> UserFlowContext:
            return UserFlowContext.from_setup_context(
                setup_ctx=context,
                chat=(
                    form_exit_context.last_update.chat
                    if isinstance(form_exit_context.last_update, tg.Message)
                    else None
                ),
                user=form_exit_context.last_update.from_user,
                last_update_content=form_exit_context.last_update,
            )

        async def on_form_completed(form_exit_context: ComponentsFormExitContext):
            user = form_exit_context.last_update.from_user
            if self.results_export.echo_to_user:
                try:
                    user_lang = (
                        await context.language_store.get_user_language(user)
                        if context.language_store is not None
                        else None
                    )
                    text = self._form.result_to_html(result=form_exit_context.result, lang=user_lang)
                    await context.bot.send_message(chat_id=user.id, text=text, parse_mode="HTML")
                except Exception:
                    logger.exception("Error echoing form result to user")
            if self.results_export.to_chat is not None:
                try:
                    feedback_handler = (
                        context.feedback_handlers.get(self.results_export.to_chat.chat_id)
                        if self.results_export.to_chat.via_feedback_handler
                        else None
                    )
                    admin_lang = context.language_store.default_language if context.language_store is not None else None
                    text = self._form.result_to_html(result=form_exit_context.result, lang=admin_lang)
                    if feedback_handler is not None:
                        await feedback_handler.emulate_user_message(
                            bot=context.bot,
                            user=form_exit_context.last_update.from_user,
                            text=text,
                            attachment=None,
                            no_response=True,
                            send_user_identifier_message=self.results_export.user_attribution
                            != FormResultUserAttribution.NONE,
                            parse_mode="HTML",
                        )
                    else:
                        user_id_text: Optional[str] = None
                        if self.results_export.user_attribution == FormResultUserAttribution.FULL:
                            user_id_text = telegram_user_link(form_exit_context.last_update.from_user)
                        elif self.results_export.user_attribution == FormResultUserAttribution.NAME:
                            user_id_text = form_exit_context.last_update.from_user.full_name
                        elif self.results_export.user_attribution == FormResultUserAttribution.UNIQUE_ID:
                            user_id_text = emoji_hash(
                                form_exit_context.last_update.from_user.id,
                                bot_prefix=self.block_id,
                                length=6,
                            )
                        if user_id_text:
                            text = user_id_text + "\n\n" + text
                        await context.bot.send_message(
                            chat_id=self.results_export.to_chat.chat_id,
                            text=text,
                            parse_mode="HTML",
                        )
                except Exception:
                    logger.exception("Error sending form result to admin chat")

            # TODO: more result export options
            # + more export options: Airtable, Google Sheets, Trello
            # + save to internal storage to show in Constructor UI
            if self.form_completed_next_block_id is not None:
                await context.enter_block(
                    self.form_completed_next_block_id,
                    _user_flow_context_for_next_block(form_exit_context),
                )

        async def on_form_cancelled(form_exit_context: ComponentsFormExitContext):
            # TODO: maybe save not completed form in a separate storage?
            if self.form_cancelled_next_block_id is not None:
                await context.enter_block(
                    self.form_cancelled_next_block_id,
                    _user_flow_context_for_next_block(form_exit_context),
                )

        self._form_handler.setup(
            bot=context.bot,
            on_form_completed=on_form_completed,
            on_form_cancelled=on_form_cancelled,
        )

        # NOTE: not exporting commands like /skip and /cancel because they are only form-specific
        return SetupResult.empty()

    async def enter(self, context: UserFlowContext) -> None:
        await self._form_handler.start(
            bot=context.bot,
            user=context.user,
            initial_form_result=None,
            separate_field_prompt_message=True,
        )


def join_localizable_texts(msgs: Sequence[LocalizableText], sep: str) -> LocalizableText:
    if not msgs:
        raise ValueError("Nothing to join")

    def _join_str(strings: list[str]) -> str:
        return sep.join([s for s in strings if s])

    if all(isinstance(msg, str) for msg in msgs):
        return _join_str(cast(list[str], msgs))
    else:
        if any(isinstance(msg, str) for msg in msgs):
            raise ValueError("All msgs must be strings or multilang texts, not mixed")
        multilang_msgs = cast(list[MultilangText], msgs)
        multilang_msgs_aggregated = {lang: [localization] for lang, localization in multilang_msgs[0].items()}
        for msg in multilang_msgs[1:]:
            for key, localizations in multilang_msgs_aggregated.items():
                if key not in msg:
                    raise ValueError(f"All msgs must be localized to the same languages, but {msg} misses {key!r}")
                localizations.append(msg[key])
        return {lang: _join_str(localization) for lang, localization in multilang_msgs_aggregated.items()}
