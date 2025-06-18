import abc
from enum import Enum
from typing import Any, Literal, Optional, Sequence, Union, cast

from pydantic import BaseModel, ConfigDict, model_validator
from telebot import types as tg
from telebot_components.feedback import FeedbackConfig as ComponentsFeedbackConfig
from telebot_components.feedback import UserAnonymization as ComponentsUserAnonymization
from telebot_components.form.field import (
    DynamicOption,
    FormField,
    FormFieldResultFormattingOpts,
    PlainTextField,
)
from telebot_components.form.field import (
    DynamicSingleSelectFieldFull as DynamicSingleSelectField,
)
from telebot_components.form.form import Form as ComponentsForm
from telebot_components.form.form import FormBranch
from telebot_components.form.handler import FormExitContext as ComponentsFormExitContext
from telebot_components.form.handler import FormHandler as ComponentsFormHandler
from telebot_components.form.handler import (
    FormHandlerConfig as ComponentsFormHandlerConfig,
)
from telebot_components.language import any_text_to_str
from telebot_components.utils import emoji_hash, telegram_html_escape
from typing_extensions import Self

from telebot_constructor.store.form_results import (
    RESERVED_FORM_FIELD_IDS,
    USER_KEY,
    BotSpecificFormResultsStore,
    FormResult,
    empty_form_result,
)
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
from telebot_constructor.utils import (
    AnyChatId,
    format_telegram_user,
    telegram_user_link,
    validate_unique,
    without_nones,
)
from telebot_constructor.utils.pydantic import (
    ExactlyOneNonNullFieldModel,
    LocalizableText,
    MultilangText,
)

# region: form fields
# note that the form component offers a lot of dirrefeent kinds of fields,
# and here we only support a subset of them;

# semantically, the classes here are "configs", while the actual
# objects that go into FormHandler are "fields"
# e.g. "XFieldConfig" instance stores stores info needed to create XField instance


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

    def construct_field(self) -> DynamicSingleSelectField:
        return DynamicSingleSelectField(
            invalid_enum_value_error_msg=self.invalid_enum_error_msg,
            default_options=[DynamicOption(id=opt.id, label=opt.label) for opt in self.options],
            **self.base_field_kwargs(),  # type: ignore
        )


class FormFieldConfig(ExactlyOneNonNullFieldModel):
    """Wrapper object for all kinds of fields; see individual classes for details on each field's specifics"""

    plain_text: Optional[PlainTextFormFieldConfig] = None
    single_select: Optional[SingleSelectFormFieldConfig] = None

    def specific_config(self) -> BaseFormFieldConfig:
        return self.plain_text or self.single_select  # type: ignore


# endregion

# besides fields, there are "branches", i.e. sequences of fields with attached
# condition. together fields and branches are referred to as "members"


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


def flatten_fields(members: list[BranchingFormMemberConfig]) -> list[FormFieldConfig]:
    """Recursively flatten all members to a list of fields, including all branches, subbrances etc"""
    res: list[FormFieldConfig] = []
    for m in members:
        if m.field is not None:
            res.append(m.field)
        elif m.branch is not None:
            res.extend(flatten_fields(m.branch.members))
    return res


class FormMessages(BaseModel):
    form_start: LocalizableText
    cancel_command_is: LocalizableText
    field_is_skippable: LocalizableText
    field_is_not_skippable: LocalizableText
    please_enter_correct_value: LocalizableText
    unsupported_command: LocalizableText

    # for easier frontend validation
    model_config = ConfigDict(extra="forbid")


# region: form result processing / export configutation


class FormResultsExportToChatConfig(BaseModel):
    chat_id: AnyChatId | None
    via_feedback_handler: bool


USER_EMOJI_HASH_LEN = 6


class FormResultUserAttribution(Enum):
    NONE = "none"  # no data collected from user
    UNIQUE_ID = "unique_id"  # only a unique anonymized ID
    NAME = "name"  # only telegram name
    FULL = "full"  # telegram name, username, user id

    def should_send_user_identifier(self, fh: ComponentsFeedbackConfig) -> bool:
        """
        Based on the level attribution, decide if it's safe to send user identifier to a given
        feedback handler without revealing more info than we want. Doesn't account for integrations,
        but we're not using them in the constructor!
        """
        match self:
            case self.FULL:
                return True
            case self.NAME:
                return fh.user_anonymization in {ComponentsUserAnonymization.FULL, ComponentsUserAnonymization.LEGACY}
            case self.UNIQUE_ID:
                return fh.user_anonymization == ComponentsUserAnonymization.FULL
        return False

    def user_html(self, user: tg.User, form_block_id: str) -> str | None:
        match self:
            case FormResultUserAttribution.FULL:
                return telegram_user_link(user)
            case FormResultUserAttribution.NAME:
                return telegram_html_escape(user.full_name)
            case FormResultUserAttribution.UNIQUE_ID:
                return telegram_html_escape(emoji_hash(user.id, bot_prefix=form_block_id, length=USER_EMOJI_HASH_LEN))
            case _:
                return None

    def user_plain(self, user: tg.User, form_block_id: str) -> str | None:
        match self:
            case FormResultUserAttribution.FULL:
                return format_telegram_user(user, with_id=True)
            case FormResultUserAttribution.NAME:
                return user.full_name
            case FormResultUserAttribution.UNIQUE_ID:
                return emoji_hash(user.id, bot_prefix=form_block_id, length=USER_EMOJI_HASH_LEN)
            case _:
                return None


class FormResultsExport(BaseModel):
    user_attribution: FormResultUserAttribution = FormResultUserAttribution.NONE
    echo_to_user: bool
    to_chat: Optional[FormResultsExportToChatConfig]
    to_store: bool = False  # default for backwards compatibility

    # deprecated, use user_attribution instead
    is_anonymous: Optional[bool] = None

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


# endregion


# to ensure unique single select field -> form attribution
# see the comment in the field's construction method
FORM_ID_BY_SINGLE_SELECT_FIELD_ID = dict[str, str]()


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
        form_id_error_prefix = f"Form block {self.block_id!r} error: "

        if not self.members:
            raise ValueError(form_id_error_prefix + "Must contain at least one member field")

        all_field_configs = flatten_fields(self.members)
        validate_unique(
            [f.specific_config().id for f in all_field_configs],
            items_name=f"field ids for form {self.block_id!r}",
            prefix=form_id_error_prefix,
        )
        self._field_names = {f.specific_config().id: f.specific_config().name for f in all_field_configs}

        for f in all_field_configs:
            field_id = f.specific_config().id
            if field_id in RESERVED_FORM_FIELD_IDS:
                raise ValueError(form_id_error_prefix + f"Field id {field_id!r} is reserved")
            if f.single_select is not None:
                if self.block_id != FORM_ID_BY_SINGLE_SELECT_FIELD_ID.setdefault(field_id, self.block_id):
                    raise ValueError(
                        form_id_error_prefix
                        + f"Attempt to create form block with a single select field id={field_id!r} "
                        + "that is already used in another form block! Ensure ids for single select "
                        + "fields are globally unique, e.g. by appending UUID to them"
                    )

        try:
            component_form_members: list[Union[FormField, FormBranch]] = [m.construct_member() for m in self.members]
            self._form = ComponentsForm.branching(component_form_members)
        except Exception as e:
            raise ValueError(form_id_error_prefix + "Form construction error: " + str(e))

        # real store is supplied only during setup
        self._store: BotSpecificFormResultsStore | None = None

    @property
    def store(self) -> BotSpecificFormResultsStore:
        if self._store is None:
            raise RuntimeError("Attempt to access FormBlock.store property before setup is done")
        return self._store

    async def setup(self, context: UserFlowSetupContext) -> SetupResult:
        self._store = context.form_results_store
        self._logger = context.make_instrumented_logger(__name__, self.block_id)

        cancelling_because_of_error_eng = "Something went wrong, details: {}"
        if context.language_store is not None:
            cancelling_because_of_error: LocalizableText = {
                lang: cancelling_because_of_error_eng for lang in context.language_store.languages
            }
        else:
            cancelling_because_of_error = cancelling_because_of_error_eng

        #                                          VVV impossible to generate type anntation for
        #                                              form result type, so we use Any
        self._form_handler = ComponentsFormHandler[Any, Any](
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
        context.errors_store.instrument(self._form_handler.logger)

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
            result = form_exit_context.result
            # to localize data for admins
            admin_lang = context.language_store.default_language if context.language_store is not None else None

            # first, exporting results to whenever the config tells us
            if self.results_export.echo_to_user:
                try:
                    user_lang = (
                        await context.language_store.get_user_language(user)
                        if context.language_store is not None
                        else None
                    )
                    text = self._form.result_to_html(result=result, lang=user_lang)
                    await context.bot.send_message(chat_id=user.id, text=text, parse_mode="HTML")
                except Exception:
                    self._logger.exception(f"Error sending form result back to the user: {result}")
            if self.results_export.to_chat is not None:
                try:
                    feedback_handler = (
                        context.feedback_handlers.get(self.results_export.to_chat.chat_id)
                        if self.results_export.to_chat.via_feedback_handler
                        else None
                    )
                    text = self._form.result_to_html(result=result, lang=admin_lang)
                    if feedback_handler is not None:
                        await feedback_handler.emulate_user_message(
                            bot=context.bot,
                            user=user,
                            text=text,
                            attachment=None,
                            no_response=True,
                            send_user_identifier_message=(
                                self.results_export.user_attribution.should_send_user_identifier(
                                    feedback_handler.config
                                )
                            ),
                            parse_mode="HTML",
                        )
                    else:
                        if user_id_text := self.results_export.user_attribution.user_html(user, self.block_id):
                            text = user_id_text + "\n\n" + text
                        await context.bot.send_message(
                            chat_id=self.results_export.to_chat.chat_id or context.owner_chat_id,
                            text=text,
                            parse_mode="HTML",
                        )
                except Exception:
                    self._logger.exception(f"Error sending form result to admin chat: {result}")
            if self.results_export.to_store:
                try:
                    result_dump: FormResult = empty_form_result()
                    for field_id, field_value in result.items():
                        result_dump[field_id] = self._form.fields_by_name[field_id].value_to_str(
                            field_value, admin_lang
                        )
                    if user_str := self.results_export.user_attribution.user_plain(user, self.block_id):
                        result_dump[USER_KEY] = user_str
                    await self.store.save_form_result(
                        form_block_id=self.block_id,
                        form_result=result_dump,
                        # on each form result, we update form metadata (field names and prompt) so that it's
                        # savecd separately and stored even if form is deleted or edited
                        field_names=self._field_names,
                        prompt=any_text_to_str(self.messages.form_start, language=admin_lang),
                    )
                except Exception:
                    self._logger.exception(f"Error saving form result to internal storage: {result}")

            if self.form_completed_next_block_id is not None:
                await context.enter_block(
                    self.form_completed_next_block_id,
                    _user_flow_context_for_next_block(form_exit_context),
                )

        async def on_form_cancelled(form_exit_context: ComponentsFormExitContext):
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
