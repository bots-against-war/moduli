export type TypographyType =
  | "h1"
  | "h2"
  | "h3"
  | "button-xl"
  | "button-l"
  | "button-s"
  | "menu-bold"
  | "body"
  | "body-s";

export function typography(t: TypographyType): string {
  const classes: string[] = [];

  // font
  if (["h1", "h2", "h3", "button-xl", "button-l", "button-s"].includes(t)) {
    // TODO: choose new headings font
    // classes.push("font-urbanist");
  }

  // weight
  if (t == "h1" || t == "h2") {
    classes.push("font-bold");
  } else if (t == "h3" || t.startsWith("button")) {
    classes.push("font-semibold");
  } else if (t == "menu-bold") {
    classes.push("font-medium");
  }

  switch (t) {
    case "h1":
      classes.push("text-3xl md:text-5xl");
      break;
    case "h2":
      classes.push("text-2xl md:text-4xl");
      break;
    case "h3":
      classes.push("text-xl md:text-2xl");
      break;
    case "button-xl":
      classes.push("text-lg");
      break;
    case "body-s":
      classes.push("text-md");
      break;
  }

  return classes.join(" ");
}

export const buttonPrimary = "bg-gray-900 text-white hover:bg-white hover:text-gray-900";
export const buttonSecondary = "bg-white text-gray-900 hover:bg-gray-200 shadow-secondary-btn";
export const buttonLink = "text-gray-900 p-0 hover:underline";
