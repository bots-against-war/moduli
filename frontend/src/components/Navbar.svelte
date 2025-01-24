<script lang="ts">
  import { Avatar, Button, NavBrand, Navbar, Popover } from "flowbite-svelte";
  import { t } from "svelte-i18n";
  import Logo from "../../../landing/src/routes/components/Logo.svelte";
  import { loggedInUserStore } from "../globalStateStores";
  import { landingPath } from "../routeUtils";
</script>

<Navbar fluid={true} color="primary" shadow>
  <NavBrand href={landingPath()} target="_blank">
    <Logo />
  </NavBrand>
  <slot>
    <Avatar
      id="avatar-menu"
      src={$loggedInUserStore.userpic !== null ? `data:image/png;base64,${$loggedInUserStore.userpic}` : undefined}
    />
    <Popover trigger="click" class="w-80" triggeredBy="#avatar-menu">
      <div class="flex flex-col gap-4">
        <p class="font-bold text-lg text-gray-800">
          {$loggedInUserStore.name}
          {#if $loggedInUserStore.display_username !== null}
            <br />
            <span class="font-light text-sm">@{$loggedInUserStore.display_username}</span>
          {/if}
        </p>
        <Button
          color="red"
          outline
          on:click={() => {
            // HACK: hardcoded cookie name, probaby better to call /logout endpoint and let it handle
            document.cookie = "tc_access_token=invalidated; expires=Thu, 01 Jan 1970 00:00:01 GMT; Path=/";
            window.location.reload();
          }}
        >
          {$t("navbar.logout")}
        </Button>
      </div>
    </Popover>
  </slot>
</Navbar>
