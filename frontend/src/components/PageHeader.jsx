export default function PageHeader({ title, chip, children }) {
  return (
    <header className="min-h-14 py-2.5 px-4 sm:px-5 flex-shrink-0 bg-white border-b hairline flex flex-wrap sm:flex-nowrap items-center justify-between gap-2">
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <h1 className="text-[14px] sm:text-[15px] font-semibold tracking-tight">{title}</h1>
        {chip && (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full border hairline text-neutral-500 whitespace-nowrap">{chip}</span>
        )}
      </div>
      {children && <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">{children}</div>}
    </header>
  );
}

