<script lang="ts">
  import { A } from "flowbite-svelte";
  import { twMerge } from "tailwind-merge";
  import { buttonLink, typography } from "../classes";

  export let href: string;
  export let class_: string = "";
  export let internal: boolean = false;
</script>

<A {href} target={internal ? "" : "_blank"} class={twMerge(typography("body"), buttonLink, class_)}>
  <slot />
</A>
