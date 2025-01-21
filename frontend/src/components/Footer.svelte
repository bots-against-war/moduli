<script>
  import { Dropdown, DropdownItem, Footer, FooterLinkGroup } from "flowbite-svelte";
  import { CodeBranchSolid, GithubSolid, LanguageOutline, MessagesSolid } from "flowbite-svelte-icons";
  import { t } from "svelte-i18n";
  import { setLocale } from "../i18n";
  import ActionIcon from "./ActionIcon.svelte";
  const buttonClass = "bg-none border-none hover:bg-gray-none p-0 text-inherit hover:text-inherit text-sm";
  const iconClass = "mr-1";
</script>

<Footer class="border-t-gray-100 border-t-2 py-3 mt-3">
  <FooterLinkGroup ulClass="flex flex-wrap gap-x-10 w-full justify-center items-center text-sm text-gray-500">
    <ActionIcon icon={MessagesSolid} {buttonClass} {iconClass} href="https://t.me/bots_against_war_bot" target="_blank">
      {$t("footer.contact")}
    </ActionIcon>
    <ActionIcon icon={LanguageOutline} {buttonClass} {iconClass} id="language-select-footer">
      {$t("footer.language")}
    </ActionIcon>
    <Dropdown triggeredBy="#language-select-footer">
      <DropdownItem on:click={() => setLocale("ru")}>Русский</DropdownItem>
      <DropdownItem on:click={() => setLocale("en")}>English</DropdownItem>
    </Dropdown>

    <ActionIcon
      icon={GithubSolid}
      {buttonClass}
      {iconClass}
      href="https://github.com/bots-against-war/moduli"
      target="_blank"
    >
      GitHub
    </ActionIcon>
    <ActionIcon
      icon={CodeBranchSolid}
      {buttonClass}
      {iconClass}
      href={"https://github.com/bots-against-war/moduli/releases/tag/__buildTimeReplacedVersion"}
      target="_blank"
      title="built on __buildTimeReplacedDatetime"
    >
      __buildTimeReplacedVersion
    </ActionIcon>
  </FooterLinkGroup>
</Footer>
