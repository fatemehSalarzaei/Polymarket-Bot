"use client";

import { FormEvent, useEffect, useState } from "react";
import { toast } from "sonner";

import { patchStrategySettings } from "@/lib/api-client";
import type { StrategySettings, StrategySettingsPatch } from "@/types/strategy";
import { ConfirmationModal } from "@/components/strategy/confirmation-modal";

type SettingsFormProps = {
  settings: StrategySettings | null;
  onSaved: (settings: StrategySettings) => void;
};

type FormState = {
  paper_trading_enabled: boolean;
  trading_enabled: boolean;
  kill_switch_active: boolean;
  final_window_seconds: string;
  min_edge: string;
  max_spread: string;
  max_slippage: string;
  max_order_size_usd: string;
  max_daily_loss_usd: string;
  max_data_age_seconds: string;
  order_type: StrategySettings["order_type"];
};

export function SettingsForm({ settings, onSaved }: SettingsFormProps) {
  const [form, setForm] = useState<FormState>(() => toFormState(settings));
  const [pendingPatch, setPendingPatch] = useState<StrategySettingsPatch | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm(toFormState(settings));
  }, [settings]);

  async function submit(patch: StrategySettingsPatch) {
    setSaving(true);
    try {
      const updated = await patchStrategySettings(patch);
      onSaved(updated);
      setForm(toFormState(updated));
      toast.success("Strategy settings saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save strategy settings");
    } finally {
      setSaving(false);
      setPendingPatch(null);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!settings) {
      toast.error("Strategy settings are not loaded");
      return;
    }

    const patch = buildPatch(settings, form);
    if (!Object.keys(patch).length) {
      toast.message("No settings changed");
      return;
    }

    if (isDangerousPatch(settings, patch)) {
      setPendingPatch(patch);
      return;
    }

    submit(patch);
  }

  return (
    <form className="rounded-md border border-zinc-200 bg-white p-5" onSubmit={onSubmit}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold">Settings</h3>
          <p className="text-sm text-muted">Real trading remains backend-gated and disabled by default.</p>
        </div>
        <button
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
          disabled={saving}
          type="submit"
        >
          {saving ? "Saving" : "Save"}
        </button>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <Toggle
          checked={form.paper_trading_enabled}
          label="Paper Trading"
          onChange={(value) => setForm((prev) => ({ ...prev, paper_trading_enabled: value }))}
        />
        <Toggle
          checked={form.trading_enabled}
          danger
          label="Real Trading"
          helper="Dangerous. Real trading remains disabled by default and backend-gated."
          onChange={(value) => setForm((prev) => ({ ...prev, trading_enabled: value }))}
        />
        <Toggle
          checked={form.kill_switch_active}
          danger
          label="Kill Switch"
          helper="When enabled, no paper or real orders will be created."
          onChange={(value) => setForm((prev) => ({ ...prev, kill_switch_active: value }))}
        />
        <NumberInput
          label="Final Window Seconds"
          helper="Strategy evaluates only during the final N seconds of the 15m market."
          value={form.final_window_seconds}
          onChange={(value) => setForm((prev) => ({ ...prev, final_window_seconds: value }))}
        />
        <NumberInput
          label="Min Price Gap"
          helper="Minimum difference between UP ask and DOWN ask required before paper trading."
          step="0.01"
          value={form.min_edge}
          onChange={(value) => setForm((prev) => ({ ...prev, min_edge: value }))}
        />
        <NumberInput
          label="Max Spread"
          helper="Maximum allowed spread for the selected side."
          step="0.01"
          value={form.max_spread}
          onChange={(value) => setForm((prev) => ({ ...prev, max_spread: value }))}
        />
        <NumberInput
          label="Max Slippage"
          step="0.01"
          value={form.max_slippage}
          onChange={(value) => setForm((prev) => ({ ...prev, max_slippage: value }))}
        />
        <NumberInput
          label="Max Order Size USD"
          step="1"
          value={form.max_order_size_usd}
          onChange={(value) => setForm((prev) => ({ ...prev, max_order_size_usd: value }))}
        />
        <NumberInput
          label="Max Daily Loss USD"
          step="1"
          value={form.max_daily_loss_usd}
          onChange={(value) => setForm((prev) => ({ ...prev, max_daily_loss_usd: value }))}
        />
        <NumberInput
          label="Max Data Age Seconds"
          step="1"
          value={form.max_data_age_seconds}
          onChange={(value) => setForm((prev) => ({ ...prev, max_data_age_seconds: value }))}
        />
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-700">Order Type</span>
          <select
            className="h-10 rounded-md border border-zinc-300 bg-white px-3 text-sm"
            value={form.order_type}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, order_type: event.target.value as StrategySettings["order_type"] }))
            }
          >
            <option value="FAK">FAK</option>
            <option value="FOK">FOK</option>
            <option value="GTC">GTC</option>
            <option value="GTD">GTD</option>
          </select>
        </label>
      </div>

      <ConfirmationModal
        confirmLabel="Apply"
        description="This changes a guarded trading or risk control setting. Backend safety gates still apply, but the change should be intentional."
        open={pendingPatch !== null}
        title="Confirm guarded setting"
        onCancel={() => setPendingPatch(null)}
        onConfirm={() => pendingPatch && submit(pendingPatch)}
      />
    </form>
  );
}

function Toggle({
  checked,
  danger,
  helper,
  label,
  onChange,
}: {
  checked: boolean;
  danger?: boolean;
  helper?: string;
  label: string;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex min-h-14 items-center justify-between gap-3 rounded-md border border-zinc-200 px-3 text-sm">
      <span>
        <span className="block font-medium text-zinc-700">{label}</span>
        {helper ? <span className="mt-1 block text-xs text-muted">{helper}</span> : null}
      </span>
      <input
        checked={checked}
        className={`h-5 w-5 ${danger ? "accent-red-700" : "accent-teal-700"}`}
        type="checkbox"
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  );
}

function NumberInput({
  helper,
  label,
  onChange,
  step = "1",
  value,
}: {
  helper?: string;
  label: string;
  onChange: (value: string) => void;
  step?: string;
  value: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      {helper ? <span className="text-xs text-muted">{helper}</span> : null}
      <input
        className="h-10 rounded-md border border-zinc-300 px-3 text-sm"
        inputMode="decimal"
        step={step}
        type="number"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function toFormState(settings: StrategySettings | null): FormState {
  return {
    paper_trading_enabled: settings?.paper_trading_enabled ?? true,
    trading_enabled: settings?.trading_enabled ?? false,
    kill_switch_active: settings?.kill_switch_active ?? false,
    final_window_seconds: String(settings?.final_window_seconds ?? 180),
    min_edge: settings?.min_edge ?? "0.05",
    max_spread: settings?.max_spread ?? "0.02",
    max_slippage: settings?.max_slippage ?? "0.02",
    max_order_size_usd: settings?.max_order_size_usd ?? "10",
    max_daily_loss_usd: settings?.max_daily_loss_usd ?? "50",
    max_data_age_seconds: String(settings?.max_data_age_seconds ?? 5),
    order_type: settings?.order_type ?? "FAK",
  };
}

function buildPatch(settings: StrategySettings, form: FormState): StrategySettingsPatch {
  const next: StrategySettingsPatch = {
    paper_trading_enabled: form.paper_trading_enabled,
    trading_enabled: form.trading_enabled,
    kill_switch_active: form.kill_switch_active,
    final_window_seconds: Number(form.final_window_seconds),
    min_edge: form.min_edge,
    max_spread: form.max_spread,
    max_slippage: form.max_slippage,
    max_order_size_usd: form.max_order_size_usd,
    max_daily_loss_usd: form.max_daily_loss_usd,
    max_data_age_seconds: Number(form.max_data_age_seconds),
    order_type: form.order_type,
  };

  return Object.fromEntries(
    Object.entries(next).filter(([key, value]) => String(value) !== String(settings[key as keyof StrategySettings])),
  ) as StrategySettingsPatch;
}

function isDangerousPatch(settings: StrategySettings, patch: StrategySettingsPatch) {
  if (patch.trading_enabled === true && !settings.trading_enabled) {
    return true;
  }
  if (patch.kill_switch_active !== undefined) {
    return true;
  }
  if (patch.max_order_size_usd && Number(patch.max_order_size_usd) > Number(settings.max_order_size_usd)) {
    return true;
  }
  if (patch.max_daily_loss_usd && Number(patch.max_daily_loss_usd) > Number(settings.max_daily_loss_usd)) {
    return true;
  }
  return false;
}
