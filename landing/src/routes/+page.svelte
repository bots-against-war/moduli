<script lang="ts">
  import { assets } from "$app/paths";
  import { A, Button } from "flowbite-svelte";
  import { GithubSolid } from "flowbite-svelte-icons";
  import { twMerge } from "tailwind-merge";
  import { buttonLink, buttonPrimary, buttonSecondary, typography } from "./classes";
  import Logo from "./components/Logo.svelte";
  import { constructorHref, contactUsHref, githubHref } from "./utils";
  import Link from "./components/Link.svelte";

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
      title: "Safe and convenient feedback",
      subtitle: "Let people reach you and talk to them through the bot without compromising anyone’s security",
    },
    {
      logo: "form.svg",
      title: "Data collection and management",
      subtitle: "Collect applications, submissions and other kinds of forms without ever leaving Telegram",
    },
    {
      logo: "knowledge_base.svg",
      title: "Interactive knowledge base",
      subtitle:
        "Turn a boring FAQ into an interactive knowledge base, easily accessible and navigable through your bot",
    },
  ];
  const featuresData = [
    {
      logo: "visual.svg",
      title: "Visual interface",
      subtitle: "No coding skills required – create bots in a visual environment",
    },
    {
      logo: "multilang.svg",
      title: "Multilanguage bots",
      subtitle: "Bots are easily localizable – talk to users in their own language",
    },
    {
      logo: "template.svg",
      title: "Templates",
      subtitle: "Use examples to get familiar with the platform",
    },
    {
      logo: "pallette.svg",
      title: "Customization",
      subtitle: "In addition to the common functionality, you can request custom modules",
    },
    {
      logo: "statistics.svg",
      title: "Statistics",
      subtitle: "Track statistics and export available data",
    },
    {
      logo: "integration.svg",
      title: "Integrations",
      subtitle: "Integrate bots in your workflow: export data to Airtable, Google Sheets and more",
    },
    {
      logo: "github.svg",
      title: "Open source",
      subtitle: "Easily self-host for maximum security and transparency",
    },
    {
      logo: "privacy.svg",
      title: "Privacy",
      subtitle: "Bots are private-by-default, protecting identities of both users and your team members",
    },
  ];
</script>

<svelte:window on:scroll={hideHeaderOnScrollDown} bind:innerWidth />
<header
  class={`fixed top-0 left-0 w-full transition-all header-background z-20 ` + (isHeaderHidden ? "top-[-30vh]" : "")}
>
  <div>
    <div class="grid grid-cols-2 md:grid-cols-3 py-5 px-10">
      <Logo />

      <div class="hidden md:flex flex-row gap-6 justify-self-center">
        <!-- TODO: implement navigation -->
        <Link href="#use-cases" internal>use cases</Link>
        <Link href="#features" internal>features</Link>
      </div>

      <div class="flex flex-row gap-8 justify-self-end">
        <button class={twMerge(typography("body"), buttonLink)} on:click={console.log}>en</button>
        <Button
          size="sm"
          class={twMerge(typography("button-s"), buttonPrimary, "hidden md:block")}
          href={constructorHref}
        >
          Start
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
          <Link href="#use-cases" internal>use cases</Link>
          <Link href="#features" internal>features</Link>
          <Link href={githubHref} class_="mt-6"><GithubSolid /></Link>
          <div class="flex flex-col gap-4 mt-6 w-full">
            <Button
              href={contactUsHref}
              target="_blank"
              size="lg"
              class={twMerge(typography("button-xl"), buttonSecondary)}
            >
              Contact us
            </Button>
            <Button href={constructorHref} size="lg" class={twMerge(typography("button-xl"), buttonPrimary)}>
              Create bot
            </Button>
          </div>
        </div>
      </div>
    {/if}
  </div>
</header>

<main class="px-3 md:p-0">
  <!-- title -->
  <div class="w-full relative main-gradient">
    <img
      alt="background"
      src={`${assets}/main-bg-desktop-en.png`}
      class="w-full hidden md:block"
      style={`padding-top: ${Math.max((1280 - innerWidth) / 2.5, 0)}px`}
    />
    <img
      alt="background"
      src={`${assets}/main-1-mobile-en.png`}
      class="w-full block md:hidden"
      style="padding-top: 80px;"
    />

    <div class="w-full relative md:absolute top-0 my-8 md:mt-[130px]">
      <div class="flex flex-col items-center gap-7 text-center">
        <h1 class={twMerge(typography("h1"), "max-w-[350px] md:max-w-[650px]")}>
          Telegram bots for activism made easy
        </h1>
        <p class={twMerge(typography("body"), "max-w-[330px] md:max-w-[400px]")}>
          Open-source no-code platform empowers you to create and operate professional Telegram bots
        </p>
        <div class="flex flex-col md:flex-row gap-4 w-full justify-center px-[5vw]">
          <Button
            href={"https://t.me/bots_against_war_bot"}
            target="_blank"
            size="lg"
            class={twMerge(typography("button-xl"), buttonSecondary, "w-full md:w-auto")}
          >
            Contact us
          </Button>
          <Button
            href={constructorHref}
            size="lg"
            class={twMerge(typography("button-xl"), buttonPrimary, "w-full md:w-auto")}
          >
            Create bot
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

  <!-- use cases -->
  <div class="w-full flex flex-col items-center gap-10 md:gap-20">
    <h2 class={typography("h2")}>Bots as activist tools</h2>

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
          <img alt={`use case ${useCase.logo}`} src={`${assets}/icons/${useCase.logo}`} class="w-12 hidden md:block" />
          <h3 class={typography("h3")}>{useCase.title}</h3>
          <p>{useCase.subtitle}</p>
        </div>
      </div>
    {/each}
  </div>

  <!-- features -->
  <div class="mt-12 md:mt-24 w-full flex flex-col items-center gap-10 md:gap-20">
    <h2 class={typography("h2")}>Key features</h2>
    <div class="grid grid-cols-2 md:grid-cols-4 md:grid-rows-2 gap-y-16 gap-x-6 mx-6">
      {#each featuresData as feature}
        <div class="flex flex-col text-center items-center gap-4">
          <img alt={`feature ${feature.logo}`} src={`${assets}/icons/${feature.logo}`} class="w-16" />
          <div>
            <h4 class="text-xl font-urbanist font-medium">{feature.title}</h4>
            <span>{feature.subtitle}</span>
          </div>
        </div>
      {/each}
    </div>
  </div>

  <!-- cta screen -->
  <div class="w-full h-[80vh] main-gradient flex items-center justify-center">
    <div class="flex flex-col items-end">
      <img
        alt="background"
        src={`${assets}/cta-en.png`}
        class="w-[60vw]"
        style={`padding-top: ${Math.max((1280 - innerWidth) / 2.5, 0)}px`}
      />
      <Button size="sm" class={twMerge(typography("button-xl"), buttonPrimary, "mt-2 mr-3")} href={constructorHref}>
        Create bot
      </Button>
    </div>
  </div>

  <footer class="w-full">
    <div class="grid grid-cols-2 md:grid-cols-3 py-3 px-10">
      <Logo />
      <div class="justify-self-center">
        designed by <Link href="https://www.linkedin.com/in/sevenard/" class_="font-bold">Serendip.</Link>
      </div>
      <Link href={contactUsHref} class_="justify-self-end flex flex-row gap-3 items-center">
        contact us
        <img alt="telegram logo" src={`${assets}/icons/telegram-dark.svg`} class="w-6" />
      </Link>
    </div>
  </footer>
</main>

<style>
  .main-gradient {
    /* radial gradient to support larger-than body screens without a harsh boundary */
    background: radial-gradient(closest-side, #f1f1f1, 80%, white);
    /* background: radial-gradient(closest-side, red, 70%, white); */
  }

  .header-background {
    background: linear-gradient(white, 95%, transparent);
  }
</style>
