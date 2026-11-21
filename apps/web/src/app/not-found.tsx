import Link from "next/link";

export default function NotFound() {
  return (
    <main className="grid min-h-dvh place-items-center px-4 text-center">
      <div>
        <p className="text-sm text-muted">404</p>
        <h1 className="mt-1 text-xl font-semibold">This page doesn&apos;t exist.</h1>
        <Link href="/" className="mt-4 inline-block text-sm text-accent hover:underline">
          Back to Home
        </Link>
      </div>
    </main>
  );
}
