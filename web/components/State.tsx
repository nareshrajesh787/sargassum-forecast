export function Loading({ what }: { what: string }) {
  return <div className="state" role="status" aria-live="polite">Loading {what}…</div>;
}
export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="state notice" role="alert">
      Could not load data: {message}. The static API may not have been published yet; try again later.
    </div>
  );
}
export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="state">{children}</div>;
}
