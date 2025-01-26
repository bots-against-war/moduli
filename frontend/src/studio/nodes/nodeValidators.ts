import { flattenedFormFields } from "../../api/typeUtils";
import type {
  ContentBlock,
  FormBlock,
  FormBranchConfig,
  HumanOperatorBlock,
  LanguageSelectBlock,
  MenuBlock,
  SingleSelectFormFieldConfig,
} from "../../api/types";
import type { MessageFormatter } from "../../i18n";
import type { LocalizableText } from "../../types";
import { err, ok, type Result } from "../../utils";
import type { LanguageConfig } from "../stores";
import { capitalize } from "../utils";
import { formMessageName } from "./FormBlock/content";
import { getBaseFormFieldConfig } from "./FormBlock/utils";

export interface ValidationError {
  error: string | string[];
}

export function validateLocalizableText(
  text: LocalizableText,
  textName: string,
  langConfig: LanguageConfig | null,
  t: MessageFormatter,
  allowEmptyTexts: boolean = false,
): Result<null, ValidationError> {
  if (langConfig === null) {
    if (typeof text === "object") {
      return err({
        error: `${capitalize(textName)}: ${t("studio.validation.localized_but_no_langs")}`,
      });
    } else if (text.length === 0) {
      return err({ error: `${capitalize(textName)}: ${t("studio.validation.is_empty")}` });
    }
  } else if (langConfig !== null) {
    let missingLanguages: string[];
    if (typeof text === "string") {
      missingLanguages = langConfig.supportedLanguageCodes;
    } else {
      missingLanguages = langConfig.supportedLanguageCodes.filter((lang) =>
        allowEmptyTexts ? text[lang] === undefined : !text[lang],
      );
    }
    if (missingLanguages.length > 0) {
      return err({
        error: `${capitalize(textName)}: ${t("studio.validation.missing_localization_to_langs")}: ${missingLanguages.join(", ")}`,
      });
    } else {
      return ok(null);
    }
  }
  return ok(null);
}

function mergeResults(results: Result<null, ValidationError>[]): Result<null, ValidationError> {
  if (results.some((res) => !res.ok)) {
    return err({
      error: results.flatMap((res) => (res.ok ? "" : res.error.error)).filter((s) => s),
    });
  } else {
    return ok(null);
  }
}

export function validateContentBlock(
  config: ContentBlock,
  langConfig: LanguageConfig | null,
  t: MessageFormatter,
): Result<null, ValidationError> {
  const textValidationResults: Result<null, ValidationError>[] = config.contents.map((content, idx) => {
    let res: Result<null, ValidationError> = ok(null);
    if (content.text) {
      res = mergeResults([
        res,
        validateLocalizableText(content.text.text, `${t("studio.validation.text")} #${idx + 1}`, langConfig, t, true),
      ]);
    }
    if (content.attachments) {
      // TODO: attachments validation
    }
    return res;
  });
  return mergeResults(textValidationResults);
}

export function validateHumanOperatorBlock(
  config: HumanOperatorBlock,
  langConfig: LanguageConfig | null,
  t: MessageFormatter,
): Result<null, ValidationError> {
  const results: Result<null, ValidationError>[] = [];

  results.push(
    validateLocalizableText(
      config.feedback_handler_config.messages_to_user.forwarded_to_admin_ok,
      t("studio.human_operator.reponse_title"),
      langConfig,
      t,
    ),
  );
  results.push(
    validateLocalizableText(
      config.feedback_handler_config.messages_to_user.throttling,
      t("studio.human_operator.anti_spam_warning_title"),
      langConfig,
      t,
    ),
  );

  return mergeResults(results);
}

export function validateMenuBlock(
  config: MenuBlock,
  langConfig: LanguageConfig | null,

  t: MessageFormatter,
): Result<null, ValidationError> {
  const results: Result<null, ValidationError>[] = [];
  results.push(validateLocalizableText(config.menu.text, t("studio.menu.message_text_label"), langConfig, t));
  if (config.menu.config.back_label !== null) {
    results.push(
      validateLocalizableText(config.menu.config.back_label, t("studio.menu.back_button_label"), langConfig, t),
    );
  }

  if (config.menu.items.length === 0) {
    results.push(err({ error: t("studio.validation.empty_menu") }));
  }

  for (const [idx, item] of config.menu.items.entries()) {
    results.push(
      validateLocalizableText(item.label, `${t("studio.validation.menu_option")} #${idx + 1}`, langConfig, t),
    );
  }

  return mergeResults(results);
}

export function validateLanguageSelectBlock(
  config: LanguageSelectBlock,
  langConfig: LanguageConfig | null,
  t: MessageFormatter,
): Result<null, ValidationError> {
  if (config.supported_languages.length === 0) {
    return err({ error: t("studio.validation.no_langs") });
  } else if (!config.default_language) {
    return err({ error: t("studio.validation.no_default_lang") });
  } else if (!config.supported_languages.includes(config.default_language)) {
    return err({ error: t("studio.validation.default_lang_is_not_supported") });
  } else {
    return validateLocalizableText(
      config.menu_config.propmt,
      t("studio.validation.langselect_menu_prompt"),
      langConfig,
      t,
    );
  }
}

export function validateFormBlock(
  config: FormBlock,
  langConfig: LanguageConfig | null,
  t: MessageFormatter,
): Result<null, ValidationError> {
  const results: Result<null, ValidationError>[] = [];
  if (config.members.length === 0) {
    results.push(err({ error: t("studio.validation.form_empty") }));
  }
  results.push(
    ...flattenedFormFields(config.members).flatMap((field, idx) => {
      idx += 1; //  1-based indexing
      const resultfForField: Result<null, ValidationError>[] = [];
      const fieldBaseConfig = getBaseFormFieldConfig(field);
      const promptValidationResult = validateLocalizableText(
        fieldBaseConfig.prompt,
        `${t("studio.validation.form_question_in_field")} #${idx}`,
        langConfig,
        t,
      );
      resultfForField.push(promptValidationResult);
      if (promptValidationResult.ok && fieldBaseConfig.name.length === 0) {
        resultfForField.push(err({ error: `${t("studio.validation.form_untitled_field")} #${idx}` }));
      }
      if (field.single_select) {
        if (field.single_select.options.length === 0) {
          resultfForField.push(err({ error: `${t("studio.validation.form_no_options")} #${idx}` }));
        }
        resultfForField.push(
          ...field.single_select.options.map((eo, optionIdx) =>
            validateLocalizableText(
              eo.label,
              `${t("studio.validation.form_option_text")} #${optionIdx + 1} (#${idx})`,
              langConfig,
              t,
            ),
          ),
        );
      }
      return mergeResults(resultfForField);
    }),
  );

  const validationResultsForBranches: Result<null, ValidationError>[] = config.members.map((member, idx) => {
    idx += 1; //  1-based indexing
    if (!member.branch) return ok(null);
    if (member.branch.members.length === 0) {
      return err({ error: t("studio.validation.form_branch_is_empty") });
    }
    if (!member.branch.condition_match_value) {
      return err({ error: t("studio.validation.form_branch_has_no_condition") });
    }
    return ok(null);
  });
  results.push(...validationResultsForBranches);

  // validating that all branches refer to valid and distinct options from a switch field
  let currentSwitchField: SingleSelectFormFieldConfig | null = null;
  let currentBranches: [FormBranchConfig, number][] = [];

  function validateCurrentBranches(): Result<null, ValidationError> {
    const branchIndices = currentBranches.map(([_, branchIdx]) => `#${branchIdx + 1}`).join(", ");
    const branchTitle = `${t("studio.validation.form_branches")} ${branchIndices}`;
    if (currentBranches.length === 0) return ok(null);
    if (currentSwitchField === null)
      return err({ error: `${branchTitle} ${t("studio.validation.form_no_switch_field")}` });
    const currentSwitchOptionIds = currentSwitchField.options.map((o) => o.id);
    const branchConditionOptionIds = currentBranches.map(([b]) => b.condition_match_value || ""); // || "" is for type safety, every branch is validated to have non-empty value
    if (branchConditionOptionIds.some((optId) => !currentSwitchOptionIds.includes(optId))) {
      return err({
        error: `${branchTitle}: ${t("studio.validation.form_condition_mismatch")}`,
      });
    }
    if (new Set(branchConditionOptionIds).size !== branchConditionOptionIds.length) {
      return err({
        error: `${branchTitle}: ${t("studio.validation.form_duplicate_condition")}`,
      });
    }
    return ok(null);
  }

  for (const [idx, member] of config.members.entries()) {
    if (member.field) {
      if (currentBranches.length > 0) {
        results.push(validateCurrentBranches());
        currentBranches = [];
      }
      if (member.field.single_select) currentSwitchField = member.field.single_select;
      else currentSwitchField = null;
    } else if (member.branch) {
      currentBranches.push([member.branch, idx]);
    }
  }
  results.push(validateCurrentBranches());

  results.push(
    ...Object.entries(config.messages).map(([key, text]) =>
      validateLocalizableText(text, formMessageName(key, t), langConfig, t),
    ),
  );
  if (!(config.results_export.echo_to_user || config.results_export.to_chat || config.results_export.to_store)) {
    results.push(err({ error: t("studio.validation.form_no_response_processing") }));
  }
  return mergeResults(results);
}
