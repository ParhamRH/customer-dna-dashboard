"use client";
import * as React from "react";
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster, toast } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ConfirmProvider } from "@/components/confirm";
import { ApiError, errorMessage } from "@/lib/api";
import { useStoredPreference } from "@/lib/state";

type Theme = "light" | "dark" | "system";
const ThemeCtx = React.createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({ theme: "system", setTheme: () => {} });

function applyTheme(t: Theme) {
  const dark = t === "dark" || (t === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function useTheme() {
  return React.useContext(ThemeCtx);
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (e, q) => {
            // background refetch failures surface as a toast; first-load failures render inline
            if (q.state.data !== undefined && !(e instanceof ApiError && e.status === 401)) toast.error(errorMessage(e));
          },
        }),
        mutationCache: new MutationCache({
          onError: (e, _v, _c, m) => {
            if (m.options.onError) return; // the mutation handles its own error
            if (e instanceof ApiError && e.status === 401) return;
            toast.error(errorMessage(e));
          },
        }),
        defaultOptions: {
          queries: {
            staleTime: 20_000,
            refetchOnWindowFocus: false,
            retry: (n, e) => !(e instanceof ApiError && [401, 403, 404, 422].includes(e.status)) && n < 2,
          },
        },
      }),
  );
  const [theme, storeTheme] = useStoredPreference<Theme>("bdna-theme", "system", ["light", "dark", "system"]);
  // The inline script in the root layout applies the stored theme before first paint; here we
  // only follow OS changes while "system" is chosen.
  React.useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);
  const setTheme = React.useCallback(
    (t: Theme) => {
      document.documentElement.dataset.theme = t;
      storeTheme(t);
      applyTheme(t);
    },
    [storeTheme],
  );

  return (
    <ThemeCtx.Provider value={{ theme, setTheme }}>
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <ConfirmProvider>
            {children}
            <Toaster
              position="bottom-right"
              toastOptions={{
                classNames: {
                  toast: "!bg-surface !text-ink !border !border-line !shadow-pop !rounded-md !font-sans",
                  description: "!text-muted",
                },
              }}
            />
          </ConfirmProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeCtx.Provider>
  );
}
