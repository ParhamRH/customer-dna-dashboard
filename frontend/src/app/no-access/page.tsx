"use client";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { logout } from "@/lib/session";
import { Wordmark } from "@/components/wordmark";

export default function NoAccess() {
  const router = useRouter();
  return (
    <main className="mx-auto grid min-h-dvh max-w-lg content-center gap-4 px-6">
      <Wordmark />
      <h1 className="mt-6 text-2xl font-semibold">No workspace yet</h1>
      <p className="text-md text-muted">
        Your account is active but is not a member of any customer workspace. Ask your customer administrator or the platform
        administrator to add you.
      </p>
      <Button
        className="justify-self-start"
        onClick={async () => {
          await logout();
          router.replace("/login");
        }}
      >
        Sign out
      </Button>
    </main>
  );
}
