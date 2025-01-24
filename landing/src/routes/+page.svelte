<script lang="ts">
  import { assets } from "$app/paths";
  import { initI18n, setLocale } from "$lib/i18n";
  import { Button } from "flowbite-svelte";
  import { GithubSolid } from "flowbite-svelte-icons";
  import { locale, t } from "svelte-i18n";
  import { twMerge } from "tailwind-merge";
  import { buttonLink, buttonPrimary, buttonSecondary, typography } from "./classes";
  import Link from "./components/Link.svelte";
  import Logo from "./components/Logo.svelte";
  import { constructorHref, contactUsHref, githubHref } from "./utils";

  initI18n();
  let otherLocale: string;
  $: otherLocale = $locale == "en" ? "ru" : "en";

  let lastScrollTop = 0;
  let isHeaderHidden = false;
  let isMenuOpen = false;

  function hideHeaderOnScrollDown() {
    if (isMenuOpen) {
      isHeaderHidden = false;
      return;
    }
    let st = window.scrollY || document.documentElement.scrollTop;
    isHeaderHidden = st > lastScrollTop;
    lastScrollTop = st <= 0 ? 0 : st;
  }

  let innerWidth: number;

  const useCasesData = [
    {
      logo: "feedback.svg",
      title: "use_cases_section.feedback.title",
      subtitle: "use_cases_section.feedback.subtitle",
    },
    {
      logo: "form.svg",
      title: "use_cases_section.form.title",
      subtitle: "use_cases_section.form.subtitle",
    },
    {
      logo: "knowledge_base.svg",
      title: "use_cases_section.kb.title",
      subtitle: "use_cases_section.kb.subtitle",
    },
  ];
  const featuresData = [
    {
      logo: "visual.svg",
      title: "features_section.visual.title",
      subtitle: "features_section.visual.subtitle",
    },
    {
      logo: "multilang.svg",
      title: "features_section.multilang.title",
      subtitle: "features_section.multilang.subtitle",
    },
    {
      logo: "template.svg",
      title: "features_section.templates.title",
      subtitle: "features_section.templates.subtitle",
    },
    {
      logo: "pallette.svg",
      title: "features_section.customization.title",
      subtitle: "features_section.customization.subtitle",
    },
    {
      logo: "statistics.svg",
      title: "features_section.stats.title",
      subtitle: "features_section.stats.subtitle",
    },
    {
      logo: "integration.svg",
      title: "features_section.integrations.title",
      subtitle: "features_section.integrations.subtitle",
    },
    {
      logo: "github.svg",
      title: "Open source",
      subtitle: "features_section.open_source.subtitle",
    },
    {
      logo: "privacy.svg",
      title: "features_section.privacy.title",
      subtitle: "features_section.privacy.subtitle",
    },
  ];

  const centeringContainerClass = "max-w-[1280px] m-auto relative px-3 md:p-0";
</script>

<svelte:window on:scroll={hideHeaderOnScrollDown} bind:innerWidth />
<header
  class={`fixed top-0 left-0 w-full transition-all header-background z-20 ` + (isHeaderHidden ? "top-[-30vh]" : "")}
>
  <div>
    <div class="grid grid-cols-2 md:grid-cols-3 py-5 px-10">
      <Logo />

      <div class="hidden md:flex flex-row gap-6 justify-self-center">
        <Link href="#use-cases" internal>{$t("use_cases")}</Link>
        <Link href="#features" internal>{$t("features")}</Link>
      </div>

      <div class="flex flex-row gap-8 justify-self-end">
        <button class={twMerge(typography("body"), buttonLink)} on:click={() => setLocale(otherLocale)}>
          {otherLocale}
        </button>
        <Button
          size="sm"
          class={twMerge(typography("button-s"), buttonPrimary, "hidden md:block")}
          href={constructorHref}
        >
          {$t("start")}
        </Button>
        <Button
          size="sm"
          class={twMerge(typography("button-s"), buttonPrimary, "block md:hidden")}
          on:click={() => (isMenuOpen = !isMenuOpen)}
        >
          {isMenuOpen ? "Close" : "Menu"}
        </Button>
      </div>
    </div>

    <!-- mobile menu -->
    {#if isMenuOpen}
      <div class="w-full h-screen flex justify-center">
        <div class="mt-6 flex flex-col gap-6 items-center w-full max-w-[350px] mx-4">
          <Link href="#use-cases" internal>{$t("use_cases")}</Link>
          <Link href="#features" internal>{$t("features")}</Link>
          <Link href={githubHref} class_="mt-6"><GithubSolid /></Link>
          <div class="flex flex-col gap-4 mt-6 w-full">
            <Button
              href={contactUsHref}
              target="_blank"
              size="lg"
              class={twMerge(typography("button-xl"), buttonSecondary)}
            >
              {$t("contact_us")}
            </Button>
            <Button href={constructorHref} size="lg" class={twMerge(typography("button-xl"), buttonPrimary)}>
              {$t("create_bot")}
            </Button>
          </div>
        </div>
      </div>
    {/if}
  </div>
</header>

<main>
  <!-- title -->
  <div class="w-full main-gradient">
    <div class={centeringContainerClass}>
      <img
        alt="background illustration (desktop)"
        src={`${assets}/main-bg-desktop-en.png`}
        class="w-full hidden md:block"
        style={`padding-top: ${Math.max((1280 - innerWidth) / 2.5, 0)}px`}
      />
      <img
        alt="background illustration (mobile)"
        src={`${assets}/main-1-mobile-en.png`}
        class="w-full block md:hidden"
        style="padding-top: 80px;"
      />

      <div class="w-full relative md:absolute top-0 my-8 md:mt-[130px]">
        <div class="flex flex-col items-center gap-7 text-center">
          <h1 class={twMerge(typography("h1"), "max-w-[350px] md:max-w-[650px]")}>
            {$t("main.title")}
          </h1>
          <p class={twMerge(typography("body"), "max-w-[330px] md:max-w-[400px]")}>
            {$t("main.subtitle")}
          </p>
          <div class="flex flex-col md:flex-row gap-4 w-full justify-center px-[5vw]">
            <Button
              href={"https://t.me/bots_against_war_bot"}
              target="_blank"
              size="lg"
              class={twMerge(typography("button-xl"), buttonSecondary, "w-full md:w-auto")}
            >
              {$t("contact_us")}
            </Button>
            <Button
              href={constructorHref}
              size="lg"
              class={twMerge(typography("button-xl"), buttonPrimary, "w-full md:w-auto")}
            >
              {$t("create_bot")}
            </Button>
          </div>
          <Link href="https://github.com/bots-against-war/moduli" class_="mt-6">
            <GithubSolid />
            <span class="ml-3">Open source</span>
          </Link>
        </div>
      </div>
      <img alt="background" src={`${assets}/main-2-mobile-en.png`} class="w-full block md:hidden" />
    </div>
  </div>

  <!-- use cases -->
  <div id="use-cases" class={centeringContainerClass}>
    <div class="flex flex-col items-center gap-10 md:gap-20">
      <h2 class={typography("h2")}>{$t("use_cases_section.title")}</h2>

      {#each useCasesData as useCase, idx}
        <div
          class={"flex mx-4 md:mx-10 gap-4 md:gap-24 items-center flex-col " +
            (idx % 2 == 0 ? `md:flex-row` : `md:flex-row-reverse`)}
        >
          <img
            alt="use case 1: feedback"
            src={`${assets}/usecase-${idx + 1}-en.jpg`}
            class="md:w-[55%] rounded-lg md:rounded-3xl"
          />
          <div
            class={"md:max-w-[400px] flex flex-col gap-1 md:gap-4 text-center md:text-left " +
              (idx % 2 == 0 ? "" : "md:text-right items-end")}
          >
            <img
              alt={`use case ${useCase.logo}`}
              src={`${assets}/icons/${useCase.logo}`}
              class="w-12 hidden md:block"
            />
            <h3 class={typography("h3")}>{$t(useCase.title)}</h3>
            <p>{$t(useCase.subtitle)}</p>
          </div>
        </div>
      {/each}
    </div>
  </div>

  <!-- features -->
  <div id="features" class={centeringContainerClass}>
    <div class="mt-12 md:mt-24 flex flex-col items-center gap-10 md:gap-20">
      <h2 class={typography("h2")}>{$t("features_section.title")}</h2>
      <div class="grid grid-cols-2 md:grid-cols-4 md:grid-rows-2 gap-y-16 gap-x-6 mx-6">
        {#each featuresData as feature}
          <div class="flex flex-col text-center items-center gap-4">
            <img alt={`feature ${feature.logo}`} src={`${assets}/icons/${feature.logo}`} class="w-16" />
            <div>
              <h4 class="text-xl font-urbanist font-medium">{$t(feature.title)}</h4>
              <span>{$t(feature.subtitle)}</span>
            </div>
          </div>
        {/each}
      </div>
    </div>
  </div>

  <!-- cta screen -->
  <div class="cta-gradient">
    <div class={centeringContainerClass}>
      <div class="min-h-[440px] md:min-h-[650px] flex items-center justify-center">
        <div class="flex flex-col items-center md:items-end">
          <img alt="cta background" src={`${assets}/cta-desktop-en.png`} class="w-[80vw] hidden md:block" />
          <img alt="cta background" src={`${assets}/cta-mobile-en.png`} class="w-[60vw] block md:hidden" />
          <Button
            size="sm"
            class={twMerge(typography("button-xl"), buttonPrimary, "mt-3 md:mr-9")}
            href={constructorHref}
          >
            {$t("create_bot")}
          </Button>
        </div>
      </div>
    </div>
  </div>
</main>

<footer class="w-full">
  <div class="flex flex-row justify-between items-center py-3 px-3">
    <Logo />
    <span class="justify-self-center text-center">
      <span class="hidden md:inline">designed by </span>
      <span class="md:hidden">dsgn → </span>
      <Link href="https://www.linkedin.com/in/sevenard/" class_="font-bold">Serendip.</Link>
    </span>
    <Link href={contactUsHref} class_="justify-self-end flex flex-row gap-3 items-center">
      <span class="hidden md:inline">{$t("contact_us_lowercase")}</span>
      <img alt="telegram logo" src={`${assets}/icons/telegram-dark.svg`} class="w-6" />
    </Link>
  </div>
</footer>

<style>
  .main-gradient {
    background: linear-gradient(white, #f7f7f7 30%, #f7f7f7 70%, white);
  }

  .cta-gradient {
    background: linear-gradient(white, #f7f7f7 60%, #f7f7f7);
  }

  .header-background {
    background: linear-gradient(white, 95%, transparent);
  }
</style>
