export default function AlertBanner({ count }: { count: number }) {
  return (
    <div className="bg-red-700 text-white text-center py-2 px-4 font-semibold tracking-wide">
      {count} unresolved alert{count !== 1 ? "s" : ""} — check Telegram
    </div>
  );
}
