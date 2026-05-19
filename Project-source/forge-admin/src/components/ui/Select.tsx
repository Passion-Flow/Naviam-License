import * as RadixSelect from "@radix-ui/react-select";

import { cn } from "@/lib/cn";

export interface SelectItem {
  value: string;
  label: string;
}

export interface SelectProps {
  value: string;
  onValueChange: (value: string) => void;
  items: SelectItem[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  id?: string;
}

// Radix Select forbids `value=""` on `<Item>` because Radix reserves the empty
// string for "clear selection". The rest of the app uses `""` to mean "any /
// no filter". Translate at this boundary so callers can keep passing `""`.
const ANY_SENTINEL = "__forge_any__";
const toRadix = (v: string) => (v === "" ? ANY_SENTINEL : v);
const fromRadix = (v: string) => (v === ANY_SENTINEL ? "" : v);

export function Select({
  value,
  onValueChange,
  items,
  placeholder,
  className,
  disabled,
  id,
}: SelectProps) {
  return (
    <RadixSelect.Root
      value={toRadix(value)}
      onValueChange={(v) => onValueChange(fromRadix(v))}
      disabled={disabled}
    >
      <RadixSelect.Trigger
        id={id}
        className={cn(
          "flex h-9 w-full items-center justify-between gap-2 rounded-lg border border-border bg-bg px-3 text-sm text-fg transition-soft data-[placeholder]:text-fg/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50",
          className,
        )}
      >
        <RadixSelect.Value placeholder={placeholder} />
        <RadixSelect.Icon>▾</RadixSelect.Icon>
      </RadixSelect.Trigger>
      <RadixSelect.Portal>
        <RadixSelect.Content
          position="popper"
          sideOffset={4}
          className="z-50 max-h-72 overflow-hidden rounded-lg border border-border bg-bg shadow-md"
        >
          <RadixSelect.Viewport className="p-1">
            {items.map((item) => (
              <RadixSelect.Item
                key={item.value || ANY_SENTINEL}
                value={toRadix(item.value)}
                className="flex cursor-pointer select-none items-center rounded px-3 py-1.5 text-sm text-fg outline-none transition-soft data-[highlighted]:bg-primary/10 data-[highlighted]:text-primary"
              >
                <RadixSelect.ItemText>{item.label}</RadixSelect.ItemText>
              </RadixSelect.Item>
            ))}
          </RadixSelect.Viewport>
        </RadixSelect.Content>
      </RadixSelect.Portal>
    </RadixSelect.Root>
  );
}
