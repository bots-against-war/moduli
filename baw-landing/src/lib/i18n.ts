import { addMessages, init, locale } from "svelte-i18n";
import en from "../locales/en.json";
import ru from "../locales/ru.json";

const LOCALSTORAGE_KEY = "locale";

export function initI18n() {
  addMessages("ru", ru);
  addMessages("en", en);

  let savedLocale: string | null = null;
  try {
    savedLocale = localStorage.getItem(LOCALSTORAGE_KEY) || window.navigator.language.split("-")[0];
    if (savedLocale !== "en" && savedLocale !== "ru") {
      savedLocale = null;
    }
  } catch {}

  init({
    fallbackLocale: "en",
    initialLocale: savedLocale || "en",
  });
}

export function setLocale(loc: string) {
  locale.set(loc);
  try {
    localStorage.setItem(LOCALSTORAGE_KEY, loc);
  } catch {}
}
