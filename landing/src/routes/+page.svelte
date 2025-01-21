<script lang="ts">
  import { A, Button } from "flowbite-svelte";
  import { GithubSolid } from "flowbite-svelte-icons";
  import { twMerge } from "tailwind-merge";
  import { buttonLink, buttonPrimary, buttonSecondary, typography } from "./classes";
  import Logo from "./components/Logo.svelte";
  import { constructorHref } from "./utils";

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
</script>

<svelte:window on:scroll={hideHeaderOnScrollDown} />
<header class={"fixed top-0 w-full transition-all header-background " + (isHeaderHidden ? "top-[-30vh]" : "")}>
  <div>
    <div class="grid grid-cols-2 md:grid-cols-3 py-5 px-10">
      <Logo />

      <div class="hidden md:flex flex-row gap-6 justify-self-center">
        <!-- TODO: implement navigation -->
        <A class={twMerge(typography("body"), buttonLink)}>use cases</A>
        <A class={twMerge(typography("body"), buttonLink)}>features</A>
      </div>

      <div class="flex flex-row gap-8 justify-self-end">
        <A class={twMerge(typography("body"), buttonLink)}>en</A>
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
          <A class={twMerge(typography("body"), buttonLink)}>use cases</A>
          <A class={twMerge(typography("body"), buttonLink)}>features</A>
          <A
            href="https://github.com/bots-against-war/moduli"
            target="_blank"
            class={twMerge(typography("body"), buttonLink, "mt-6")}
          >
            <GithubSolid />
          </A>
          <div class="flex flex-col gap-4 mt-6 w-full">
            <Button
              href={"https://t.me/bots_against_war_bot"}
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
  <div class="w-full h-screen flex items-center justify-center">
    <div class="flex flex-col items-center gap-7 text-center">
      <h1 class={twMerge(typography("h1"), "max-w-[350px] md:max-w-[650px]")}>Telegram bots for activism made easy</h1>
      <p class={twMerge(typography("body"), "max-w-[330px] md:max-w-[400px]")}>
        Open-source no-code platform empowers you to create and operate professional Telegram bots
      </p>
      <div class="flex flex-col md:flex-row gap-4 w-full justify-center">
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
      <A
        href="https://github.com/bots-against-war/moduli"
        target="_blank"
        class={twMerge(typography("body"), buttonLink, "mt-6")}
      >
        <GithubSolid />
        <span class="ml-3">We are open source</span>
      </A>
    </div>
  </div>

  <div class="w-full h-screen flex flex-row items-center justify-center">
    <h1 class={typography("h1")}>Hello world!</h1>
  </div>
</main>

<style>
  .header-background {
    background: linear-gradient(to bottom, white, 99%, transparent);
  }
</style>
