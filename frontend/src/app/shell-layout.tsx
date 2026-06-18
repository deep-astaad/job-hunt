// Thin wrapper kept for import compatibility; AppShell in layout.tsx handles the shell.
export function ShellLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
