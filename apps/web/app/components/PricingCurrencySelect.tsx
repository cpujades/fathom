import type { PricingCurrency } from "../content/pricing";

type PricingCurrencySelectProps = {
  className: string;
  currency: PricingCurrency;
  onChange: (currency: PricingCurrency) => void;
};

export function PricingCurrencySelect({
  className,
  currency,
  onChange
}: PricingCurrencySelectProps) {
  return (
    <label className={className}>
      <span>Currency</span>
      <select
        aria-label="Currency"
        value={currency}
        onChange={(event) => onChange(event.target.value as PricingCurrency)}
      >
        <option value="eur">EUR (€)</option>
        <option value="usd">USD ($)</option>
        <option value="gbp">GBP (£)</option>
      </select>
    </label>
  );
}
