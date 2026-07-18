export function money(amount: number, currency = "PKR"): string {
  return new Intl.NumberFormat("en-PK", { style: "currency", currency, minimumFractionDigits: 2 }).format(amount / 100);
}
export function dateTime(value: string): string {
  return new Intl.DateTimeFormat("en-PK", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
export function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
