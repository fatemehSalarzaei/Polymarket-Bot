"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { getCurrentDecision, getDecisionHistory, getStrategySettings } from "@/lib/api-client";
import type { StrategyDecision, StrategySettings } from "@/types/strategy";
import { DecisionCard } from "@/components/strategy/decision-card";
import { DecisionHistory } from "@/components/strategy/decision-history";
import { SettingsForm } from "@/components/strategy/settings-form";

export function StrategyClient() {
  const [settings, setSettings] = useState<StrategySettings | null>(null);
  const [currentDecision, setCurrentDecision] = useState<StrategyDecision | null>(null);
  const [decisions, setDecisions] = useState<StrategyDecision[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      const [settingsResult, currentResult, historyResult] = await Promise.allSettled([
        getStrategySettings(),
        getCurrentDecision(),
        getDecisionHistory(),
      ]);

      if (cancelled) {
        return;
      }

      if (settingsResult.status === "fulfilled") {
        setSettings(settingsResult.value);
      } else {
        toast.error(errorMessage(settingsResult.reason, "Failed to load strategy settings"));
      }

      if (currentResult.status === "fulfilled") {
        setCurrentDecision(currentResult.value);
      } else if (!String(currentResult.reason).includes("404")) {
        toast.error(errorMessage(currentResult.reason, "Failed to load current decision"));
      }

      if (historyResult.status === "fulfilled") {
        setDecisions(historyResult.value);
      } else {
        toast.error(errorMessage(historyResult.reason, "Failed to load decision history"));
      }

      setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="mx-auto max-w-7xl px-5 py-8">
      <div className="mb-6">
        <p className="text-sm font-semibold text-accent">Strategy and guarded controls</p>
        <h2 className="mt-1 text-3xl font-bold tracking-normal">Strategy</h2>
      </div>

      {loading ? <div className="mb-4 rounded-md border border-zinc-200 bg-white p-4 text-sm text-muted">Loading</div> : null}

      <div className="grid gap-5">
        <DecisionCard decision={currentDecision} />
        <SettingsForm settings={settings} onSaved={setSettings} />
        <DecisionHistory decisions={decisions} />
      </div>
    </section>
  );
}

function errorMessage(value: unknown, fallback: string) {
  return value instanceof Error ? value.message : fallback;
}

