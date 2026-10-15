import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto grid min-h-dvh max-w-lg content-center gap-3 px-6">
      <h1 className="text-2xl font-semibold">This page does not exist</h1>
      <p className="text-md text-muted">The link may be outdated, or the item belongs to a workspace you cannot open.</p>
      <Link href="/" className="text-accent underline underline-offset-2">
        Go to your start page
      </Link>
    </main>
  );
}
