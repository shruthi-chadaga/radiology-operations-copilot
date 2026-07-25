"use client";

import { usePathname } from "next/navigation";

import { PrimaryTabs } from "@/components/primary-tabs";

export function WorkspaceTabs() {
  return <PrimaryTabs currentPath={usePathname()} />;
}
