import type { CommandEntryPoint, UserFlowConfig } from "../api/types";
import { DEFAULT_START_COMMAND_ENTRYPOINT_ID } from "../constants";
import { generateFormFieldId, generateOptionId } from "./nodes/FormBlock/utils";
import { generateFormName } from "./nodes/defaultConfigs";
import { NodeTypeKey } from "./nodes/display";
import { boundingBox, generateNodeId, NodeKind } from "./utils";

export interface Template {
  config: UserFlowConfig;
  entryBlockId: string;
  customStartCmd: CommandEntryPoint;
}

export function applyTemplate(config: UserFlowConfig, template: Template): UserFlowConfig {
  const startCommand = config.entrypoints.find(
    (ep) => ep.command?.entrypoint_id === DEFAULT_START_COMMAND_ENTRYPOINT_ID,
  )?.command;
  if (!startCommand) {
    throw "Start command not found in the config!";
  }

  config.entrypoints.push(...template.config.entrypoints);
  config.blocks.push(...template.config.blocks);
  if (startCommand.next_block_id === null) {
    startCommand.next_block_id = template.entryBlockId;
    config.node_display_coords = { ...config.node_display_coords, ...template.config.node_display_coords };
  } else {
    template.customStartCmd.next_block_id = template.entryBlockId;
    template.config.node_display_coords[template.customStartCmd.entrypoint_id] = { x: 0, y: 0 };

    config.entrypoints.push({ command: template.customStartCmd });
    const existingBbox = boundingBox(config.node_display_coords, 250, 200);
    const templateBbox = boundingBox(template.config.node_display_coords, 250, 200);

    // we want to move only in x direction for simplicity
    console.debug("existing bbox", existingBbox);
    console.debug("template bbox", templateBbox);
    let xOffset = 0;
    if (!(existingBbox.yMax < templateBbox.yMin || existingBbox.yMin > templateBbox.yMax)) {
      // there's an intersection along y axis
      const xMargin = 30;
      const xDeltaRight = Math.max(existingBbox.xMax - templateBbox.xMin, 0.0);
      const xDeltaLeft = Math.max(templateBbox.xMax - existingBbox.xMin, 0.0);
      console.debug("delta right", xDeltaRight, "delta left", xDeltaLeft);
      xOffset = xDeltaRight < xDeltaLeft ? xDeltaRight + xMargin : -xDeltaLeft - xMargin;
      console.debug("offset", xOffset);
    }
    config.node_display_coords = {
      ...config.node_display_coords,
      ...Object.fromEntries(
        Object.entries(template.config.node_display_coords).map(([key, { x, y }]) => [key, { x: x + xOffset, y }]),
      ),
    };
  }
  return config;
}

export function contentOnlyTemplate(): Template {
  const contentBlockId = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const config: UserFlowConfig = {
    entrypoints: [],
    blocks: [
      {
        content: {
          block_id: contentBlockId,
          contents: [
            {
              text: {
                text: "**«Римские каникулы»** (англ. _Roman Holiday_) — американская романтическая комедия с элементами мелодрамы 1953 года. Фильм снят по литературному сценарию Далтона Трамбо, режиссёр и продюсер Уильям Уайлер. В главной мужской роли Грегори Пек, в главной женской роли Одри Хепбёрн (первая значительная роль Хепбёрн, которая принесла актрисе премию «Оскар»).\n\n**Сюжет**\n\n>Анна — юная принцесса неназванного европейского государства, которая прибывает в Рим в рамках своего широко разрекламированного дипломатического тура по странам Европы. Время её расписано по минутам, а титул предполагает строгое следование этикету и тяготящие её длинные церемонии. На официальном балу она принимает первых лиц Италии и послов других стран, а после приёма — зная, что завтрашний день тоже будет представлять собой череду официальных визитов и пресс-конференций — срывается, не в силах более выносить груз королевских обязанностей, которые ограничивают её свободу. Чтобы остановить её истерику, придворный врач делает Анне укол нового снотворного и седативного средства, уверяя, что ей это наверняка поможет.\n>...\n>Ввиду своего увлечения, Джо принимает решение не публиковать статью о принцессе. Его коллеги в недоумении — босс считает, что Брэдли лукавит и таким образом пытается поднять цену на материал, а Ирвин, показав другу проявленные фотографии, — прямо заявляет, что тот сошёл с ума, выпуская из рук такую сенсацию. Фильм заканчивается ||невесёлой сценой пресс-конференции, на которой среди прочих журналистов Анна замечает Ирвина и Джо. На пресс-конференции она словно обращается напрямую к Джо, вкладывая в свои слова двойной смысл — так, на вопрос о том, какой город из всей поездки ей понравился больше всего, Анна вопреки подсказкам советников говорит, что никогда не забудет Рим и будет до конца жизни хранить память о нём.||\n\n[Википедия](https://ru.wikipedia.org/wiki/%D0%A0%D0%B8%D0%BC%D1%81%D0%BA%D0%B8%D0%B5_%D0%BA%D0%B0%D0%BD%D0%B8%D0%BA%D1%83%D0%BB%D1%8B)",
                markup: "markdown",
              },
              attachments: [],
            },
          ],
          next_block_id: null,
        },
        human_operator: null,
        menu: null,
        form: null,
        language_select: null,
        error: null,
      },
    ],
    node_display_coords: {},
  };
  config.node_display_coords[contentBlockId] = { x: 0, y: 130 };
  return {
    config,
    entryBlockId: contentBlockId,
    customStartCmd: {
      entrypoint_id: generateNodeId(NodeKind.entrypoint, NodeTypeKey.command),
      command: "content",
      next_block_id: null,
      scope: "private",
    },
  };
}

export function basicShowcaseTemplate(): Template {
  const menuBlockId = generateNodeId(NodeKind.block, NodeTypeKey.menu);
  const contentAboutBlockId = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const contentQuestionBlockId = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const operatorBlockId = generateNodeId(NodeKind.block, NodeTypeKey.human_operator);
  return {
    config: {
      entrypoints: [],
      blocks: [
        {
          content: null,
          human_operator: null,
          menu: {
            block_id: menuBlockId,
            menu: {
              text: "Привет! Спасибо, что обратились к нам. Какой у вас вопрос? ",
              items: [
                {
                  label: "Адрес",
                  submenu: null,
                  next_block_id: contentAboutBlockId,
                  link_url: null,
                },
                {
                  label: "Вопрос",
                  submenu: null,
                  next_block_id: contentQuestionBlockId,
                  link_url: null,
                },
              ],
              config: {
                mechanism: "inline_buttons",
                back_label: null,
                lock_after_termination: false,
              },
            },
          },
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentAboutBlockId,
            contents: [
              {
                text: {
                  text: "Проспект Мира, 16",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentQuestionBlockId,
            contents: [
              {
                text: {
                  text: "Привет! Спасибо, что обратились к нам. Какой у вас вопрос? ",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: operatorBlockId,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: null,
          human_operator: {
            block_id: operatorBlockId,
            catch_all: false,
            feedback_handler_config: {
              admin_chat_id: null,
              forum_topic_per_user: false,
              anonimyze_users: true,
              max_messages_per_minute: 20,
              messages_to_user: {
                forwarded_to_admin_ok: "Спасибо, мы вам скоро ответим!",
                throttling: "Не присылайте больше {} сообщений в минуту!",
              },
              messages_to_admin: {
                copied_to_user_ok: "Передано!",
                deleted_message_ok: "Message deleted from chat with user",
                can_not_delete_message: "Can't delete message from chat with user",
              },
              hashtags_in_admin_chat: false,
              unanswered_hashtag: null,
              hashtag_message_rarer_than: null,
              message_log_to_admin_chat: true,
            },
          },
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
      ],
      node_display_coords: {
        [menuBlockId]: {
          x: 0,
          y: 200,
        },
        [contentAboutBlockId]: {
          x: -200,
          y: 400,
        },
        [contentQuestionBlockId]: {
          x: 200,
          y: 400,
        },
        [operatorBlockId]: {
          x: 250,
          y: 600,
        },
      },
    },
    customStartCmd: {
      entrypoint_id: generateNodeId(NodeKind.entrypoint, NodeTypeKey.command),
      command: "begin",
      next_block_id: null,
      scope: "private",
      short_description: null,
    },
    entryBlockId: menuBlockId,
  };
}

export function formsTemplate(): Template {
  const contentBlockId1 = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const menuBlockId1 = generateNodeId(NodeKind.block, NodeTypeKey.menu);
  const formBlockId1 = generateNodeId(NodeKind.block, NodeTypeKey.form);
  const contentBlockId2 = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const contentBlockId3 = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const formBlockId2 = generateNodeId(NodeKind.block, NodeTypeKey.form);
  const contentBlockId4 = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const contentBlockId5 = generateNodeId(NodeKind.block, NodeTypeKey.content);

  const formName1 = generateFormName();
  const formName2 = generateFormName();

  const formFieldId1 = generateFormFieldId();
  const formFieldId2 = generateFormFieldId();
  const formFieldId3 = generateFormFieldId();
  const formFieldId4 = generateFormFieldId();
  const formFieldId5 = generateFormFieldId();
  const formFieldId6 = generateFormFieldId();
  const formFieldId7 = generateFormFieldId();
  const formFieldId8 = generateFormFieldId();
  const formFieldId9 = generateFormFieldId();
  const formFieldId10 = generateFormFieldId();
  const formFieldId11 = generateFormFieldId();

  const optionId1 = generateOptionId();
  const optionId2 = generateOptionId();
  const optionId3 = generateOptionId();
  const optionId4 = generateOptionId();

  return {
    customStartCmd: {
      entrypoint_id: generateNodeId(NodeKind.entrypoint, NodeTypeKey.command),
      command: "form",
      next_block_id: null,
      scope: "private",
      short_description: null,
    },
    entryBlockId: contentBlockId1,
    config: {
      entrypoints: [],
      blocks: [
        {
          content: {
            block_id: contentBlockId1,
            contents: [
              {
                text: {
                  text: 'Добрый день! Это чат-бот приюта для кошек "Дом". Здесь вы сможете подать заявку, чтобы передать питомцев в приют или взять их домой. ',
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: menuBlockId1,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: null,
          human_operator: null,
          menu: {
            block_id: menuBlockId1,
            menu: {
              text: "Что вас интересует?",
              items: [
                {
                  label: "Передать питомца",
                  submenu: null,
                  next_block_id: formBlockId1,
                  link_url: null,
                },
                {
                  label: "Взять питомца",
                  submenu: null,
                  next_block_id: formBlockId2,
                  link_url: null,
                },
              ],
              config: {
                mechanism: "inline_buttons",
                back_label: null,
                lock_after_termination: false,
              },
            },
          },
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: null,
          human_operator: null,
          menu: null,
          form: {
            block_id: formBlockId1,
            form_name: formName1,
            members: [
              {
                field: {
                  plain_text: {
                    id: formFieldId1,
                    name: "Имя",
                    prompt: "Как вас зовут? ",
                    is_required: true,
                    result_formatting: "auto",
                    is_long_text: false,
                    empty_text_error_msg: "Ответ не может быть пустым.",
                  },
                  single_select: null,
                },
                branch: null,
              },
              {
                field: {
                  plain_text: {
                    id: formFieldId2,
                    name: "Контакт",
                    prompt: "Как с вами связаться? ",
                    is_required: true,
                    result_formatting: "auto",
                    is_long_text: false,
                    empty_text_error_msg: "Ответ не может быть пустым.",
                  },
                  single_select: null,
                },
                branch: null,
              },
              {
                field: {
                  plain_text: null,
                  single_select: {
                    id: formFieldId3,
                    name: "Питомец",
                    prompt: "Вы хотите передать в приют:",
                    is_required: true,
                    result_formatting: "auto",
                    options: [
                      {
                        id: optionId1,
                        label: "Кошка/Кот",
                      },
                      {
                        id: optionId2,
                        label: "Другой питомец",
                      },
                    ],
                    invalid_enum_error_msg:
                      "Ответ должен быть одним из предложенных в меню вариантов. Если вы не видите меню, нажмите на кнопку с 4 точками рядом с полем ввода.",
                  },
                },
                branch: null,
              },
              {
                field: null,
                branch: {
                  members: [
                    {
                      field: {
                        plain_text: {
                          id: formFieldId4,
                          name: "Описание",
                          prompt:
                            "Опишите питомца (имя, возраст, вес, порода, цвет шерсти и глаз, заболевания, истории из жизни и другое). ",
                          is_required: true,
                          result_formatting: "auto",
                          is_long_text: false,
                          empty_text_error_msg: "Ответ не может быть пустым.",
                        },
                        single_select: null,
                      },
                      branch: null,
                    },
                  ],
                  condition_match_value: optionId1,
                },
              },
              {
                field: null,
                branch: {
                  members: [
                    {
                      field: {
                        plain_text: {
                          id: formFieldId5,
                          name: "Другие животные",
                          prompt:
                            "Мы принимаем только кошек и котов, но если вы опишите ваше животное, возможно мы сможем подсказать к кому обратиться. ",
                          is_required: true,
                          result_formatting: "auto",
                          is_long_text: false,
                          empty_text_error_msg: "Ответ не может быть пустым.",
                        },
                        single_select: null,
                      },
                      branch: null,
                    },
                  ],
                  condition_match_value: optionId2,
                },
              },
            ],
            messages: {
              form_start: "Пожалуйста, заполните форму и мы свяжемся с вами в ближайшие дни. Спасибо! ",
              cancel_command_is: "/cancel — отменить заполнение формы.",
              field_is_skippable: "/skip — пропустить поле.",
              field_is_not_skippable: "Это поле нельзя пропустить!",
              please_enter_correct_value: "Пожалуйста, исправьте значение.",
              unsupported_command: "Команда не поддерживается! При заполнении формы доступны команды: /skip, /cancel",
            },
            results_export: {
              user_attribution: "full",
              echo_to_user: true,
              to_chat: null,
              to_store: true,
              is_anonymous: null,
            },
            form_completed_next_block_id: contentBlockId2,
            form_cancelled_next_block_id: contentBlockId3,
          },
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentBlockId2,
            contents: [
              {
                text: {
                  text: "Спасибо за ваши ответы! ",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentBlockId3,
            contents: [
              {
                text: {
                  text: "Вы всегда можете вернуться к заполнению формы. Спасибо! ",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: null,
          human_operator: null,
          menu: null,
          form: {
            block_id: formBlockId2,
            form_name: formName2,
            members: [
              {
                field: {
                  plain_text: {
                    id: formFieldId6,
                    name: "Имя",
                    prompt: "Как вас зовут? ",
                    is_required: true,
                    result_formatting: "auto",
                    is_long_text: false,
                    empty_text_error_msg: "Ответ не может быть пустым.",
                  },
                  single_select: null,
                },
                branch: null,
              },
              {
                field: {
                  plain_text: {
                    id: formFieldId7,
                    name: "Контакт",
                    prompt: "Как с вами связаться? ",
                    is_required: true,
                    result_formatting: "auto",
                    is_long_text: false,
                    empty_text_error_msg: "Ответ не может быть пустым.",
                  },
                  single_select: null,
                },
                branch: null,
              },
              {
                field: {
                  plain_text: null,
                  single_select: {
                    id: formFieldId8,
                    name: "Питомец",
                    prompt: "Вы хотите взять из приюта:",
                    is_required: true,
                    result_formatting: "auto",
                    options: [
                      {
                        id: optionId3,
                        label: "Кошка/Кот",
                      },
                      {
                        id: optionId4,
                        label: "Другой питомец",
                      },
                    ],
                    invalid_enum_error_msg:
                      "Ответ должен быть одним из предложенных в меню вариантов. Если вы не видите меню, нажмите на кнопку с 4 точками рядом с полем ввода.",
                  },
                },
                branch: null,
              },
              {
                field: null,
                branch: {
                  members: [
                    {
                      field: {
                        plain_text: {
                          id: formFieldId9,
                          name: "Описание",
                          prompt: "Опишите питомца, которого вы хотели бы взять. ",
                          is_required: true,
                          result_formatting: "auto",
                          is_long_text: false,
                          empty_text_error_msg: "Ответ не может быть пустым.",
                        },
                        single_select: null,
                      },
                      branch: null,
                    },
                    {
                      field: {
                        plain_text: {
                          id: formFieldId10,
                          name: "Домашние условия ",
                          prompt:
                            "Опишите ваши домашние условия для питомца (другие животные, дети, квартира/дом и другое). ",
                          is_required: true,
                          result_formatting: "auto",
                          is_long_text: false,
                          empty_text_error_msg: "Ответ не может быть пустым.",
                        },
                        single_select: null,
                      },
                      branch: null,
                    },
                  ],
                  condition_match_value: optionId3,
                },
              },
              {
                field: null,
                branch: {
                  members: [
                    {
                      field: {
                        plain_text: {
                          id: formFieldId11,
                          name: "Другое животное",
                          prompt:
                            "Мы занимаемся только кошками, но если вы опишите животное, которое ищите, возможно мы сможем подсказать к кому обратиться. ",
                          is_required: true,
                          result_formatting: "auto",
                          is_long_text: false,
                          empty_text_error_msg: "Ответ не может быть пустым.",
                        },
                        single_select: null,
                      },
                      branch: null,
                    },
                  ],
                  condition_match_value: optionId4,
                },
              },
            ],
            messages: {
              form_start: "Пожалуйста, заполните форму и мы свяжемся с вами в ближайшие дни. Спасибо! ",
              cancel_command_is: "/cancel — отменить заполнение формы.",
              field_is_skippable: "/skip — пропустить поле.",
              field_is_not_skippable: "Это поле нельзя пропустить!",
              please_enter_correct_value: "Пожалуйста, исправьте значение.",
              unsupported_command: "Команда не поддерживается! При заполнении формы доступны команды: /skip, /cancel",
            },
            results_export: {
              user_attribution: "full",
              echo_to_user: true,
              to_chat: null,
              to_store: true,
              is_anonymous: null,
            },
            form_completed_next_block_id: contentBlockId4,
            form_cancelled_next_block_id: contentBlockId5,
          },
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentBlockId4,
            contents: [
              {
                text: {
                  text: "Спасибо за ваши ответы! ",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentBlockId5,
            contents: [
              {
                text: {
                  text: "Вы всегда можете вернуться к заполнению формы. Спасибо! ",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
      ],
      node_display_coords: {
        [contentBlockId1]: {
          x: 0,
          y: 150,
        },
        [menuBlockId1]: {
          x: 0,
          y: 450,
        },
        [formBlockId1]: {
          x: -450,
          y: 700,
        },
        [contentBlockId2]: {
          x: -600,
          y: 1000,
        },
        [contentBlockId3]: {
          x: -270,
          y: 1000,
        },
        [formBlockId2]: {
          x: 150,
          y: 700,
        },
        [contentBlockId4]: {
          x: 40,
          y: 1000,
        },
        [contentBlockId5]: {
          x: 400,
          y: 1000,
        },
      },
    },
  };
}

export function multilangTemplate(): Template {
  const langSelectBlockId = generateNodeId(NodeKind.block, NodeTypeKey.language_select);
  const contentBlockId = generateNodeId(NodeKind.block, NodeTypeKey.content);
  return {
    customStartCmd: {
      entrypoint_id: generateNodeId(NodeKind.entrypoint, NodeTypeKey.command),
      command: "begin",
      next_block_id: null,
      scope: "private",
      short_description: null,
    },
    entryBlockId: langSelectBlockId,
    config: {
      entrypoints: [],
      blocks: [
        {
          content: null,
          human_operator: null,
          menu: null,
          form: null,
          language_select: {
            block_id: langSelectBlockId,
            menu_config: {
              propmt: {
                ru: "Добрый день! На каком языке вам удобно общаться? ",
                en: "Hello! Which language would you prefer to use?",
                uz: "Salom! Qaysi tilda muloqot qilishni afzal ko'rasiz?",
              },
              is_blocking: false,
              emoji_buttons: true,
            },
            supported_languages: ["ru", "en", "uz"],
            default_language: "ru",
            language_selected_next_block_id: null,
            next_block_id: contentBlockId,
          },
          error: null,
        },
        {
          content: {
            block_id: contentBlockId,
            contents: [
              {
                text: {
                  text: {
                    ru: "Спасибо, что обратились к нам. Мы работаем ежедневно с 10 до 17. За помощью приходите к нам в офис по адресу: проспект Мира, 16.",
                    en: "Thank you for reaching out to us. We are open daily from 10 AM to 5 PM. For assistance, please visit our office at 16 Mira Avenue.",
                    uz: "Biz bilan bog'langaningiz uchun rahmat. Biz har kuni soat 10:00 dan 17:00 gacha ishlaymiz. Yordam olish uchun Mir prospekti, 16-manzilda joylashgan ofisimizga keling.",
                  },
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
      ],
      node_display_coords: {
        [langSelectBlockId]: {
          x: 0,
          y: 150,
        },
        [contentBlockId]: {
          x: -100,
          y: 300,
        },
      },
    },
  };
}

export function festivalBotTemplate(): Template {
  const menuBlockId1 = generateNodeId(NodeKind.block, NodeTypeKey.menu);
  const menuBlockId2 = generateNodeId(NodeKind.block, NodeTypeKey.menu);
  const contentBlockId1 = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const contentBlockId3 = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const contentBlockId2 = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const contentBlockId4 = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const contentBlockId5 = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const contentBlockId7 = generateNodeId(NodeKind.block, NodeTypeKey.content);
  const contentBlockId6 = generateNodeId(NodeKind.block, NodeTypeKey.content);

  return {
    customStartCmd: {
      entrypoint_id: generateNodeId(NodeKind.entrypoint, NodeTypeKey.command),
      command: "menu",
      next_block_id: null,
      scope: "private",
      short_description: null,
    },
    entryBlockId: menuBlockId1,
    config: {
      entrypoints: [],
      blocks: [
        {
          content: null,
          human_operator: null,
          menu: {
            block_id: menuBlockId1,
            menu: {
              text: "Добрый день! Мы ждем вас на фестивале тихой музыки. 1-2 января в библиотеках Центрального района. ",
              items: [
                {
                  label: "Программа 1 января",
                  submenu: null,
                  next_block_id: contentBlockId1,
                  link_url: null,
                },
                {
                  label: "Программа 2 января",
                  submenu: null,
                  next_block_id: contentBlockId2,
                  link_url: null,
                },
                {
                  label: "Билеты ",
                  submenu: null,
                  next_block_id: contentBlockId3,
                  link_url: null,
                },
                {
                  label: "Принять участие",
                  submenu: null,
                  next_block_id: menuBlockId2,
                  link_url: null,
                },
              ],
              config: {
                mechanism: "inline_buttons",
                back_label: "Назад",
                lock_after_termination: false,
              },
            },
          },
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentBlockId1,
            contents: [
              {
                text: {
                  text: "1 января\n\n- 10:00 Концерт 1 (Библиотека 1) \n- 12:00 Концерт 2 (Библиотека 2)\n- 14:00 Концерт 3 (Библиотека 1)\n- 16:00 Концерт 4 (Библиотека 2)\n- 18:00 Концерт 5 (Библиотека 3) ",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: null,
          human_operator: null,
          menu: {
            block_id: contentBlockId3,
            menu: {
              text: "Билеты на фестиваль бесплатные. Количество мест ограничено, поэтому мы просим вас заранее зарегистрироваться. ",
              items: [
                {
                  label: "1 января",
                  submenu: null,
                  next_block_id: contentBlockId4,
                  link_url: null,
                },
                {
                  label: "2 января",
                  submenu: null,
                  next_block_id: contentBlockId5,
                  link_url: null,
                },
              ],
              config: {
                mechanism: "inline_buttons",
                back_label: "⬅️️️⬅️️️⬅️️️",
                lock_after_termination: false,
              },
            },
          },
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: null,
          human_operator: null,
          menu: {
            block_id: menuBlockId2,
            menu: {
              text: "В какой роли вы хотите принять участие в фестивале? ",
              items: [
                {
                  label: "Музыкант",
                  submenu: null,
                  next_block_id: contentBlockId6,
                  link_url: null,
                },
                {
                  label: "Лектор",
                  submenu: null,
                  next_block_id: contentBlockId7,
                  link_url: null,
                },
              ],
              config: {
                mechanism: "inline_buttons",
                back_label: "⬅️",
                lock_after_termination: false,
              },
            },
          },
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentBlockId2,
            contents: [
              {
                text: {
                  text: "2 января\n\n- 10:00 Концерт 1 (Библиотека 1)\n- 12:00 Концерт 2 (Библиотека 2)\n- 14:00 Концерт 3 (Библиотека 1)\n- 16:00 Концерт 4 (Библиотека 2)\n- 18:00 Концерт 5 (Библиотека 3)",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentBlockId4,
            contents: [
              {
                text: {
                  text: "Ждем вас! Ссылка для регистрации на все мероприятия 1 января: ",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentBlockId5,
            contents: [
              {
                text: {
                  text: "Ждем вас! Ссылка для регистрации на все мероприятия 2 января: ",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentBlockId7,
            contents: [
              {
                text: {
                  text: "Пожалуйста, отправьте примеры ваших выступлений нам на почту: ",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
        {
          content: {
            block_id: contentBlockId6,
            contents: [
              {
                text: {
                  text: "К сожалению, музыкальная программа этого года сформирована. Приходите к нам слушателями. ",
                  markup: "markdown",
                },
                attachments: [],
              },
            ],
            next_block_id: null,
          },
          human_operator: null,
          menu: null,
          form: null,
          language_select: null,
          error: null,
        },
      ],
      node_display_coords: {
        [menuBlockId1]: {
          x: 0,
          y: 150,
        },
        [contentBlockId1]: {
          x: -450,
          y: 600,
        },
        [contentBlockId3]: {
          x: 400,
          y: 600,
        },
        [menuBlockId2]: {
          x: 1000,
          y: 600,
        },
        [contentBlockId2]: {
          x: -50,
          y: 600,
        },
        [contentBlockId4]: {
          x: 100,
          y: 1000,
        },
        [contentBlockId5]: {
          x: 500,
          y: 1000,
        },
        [contentBlockId7]: {
          x: 1200,
          y: 1000,
        },
        [contentBlockId6]: {
          x: 850,
          y: 1000,
        },
      },
    },
  };
}
