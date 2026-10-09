"use client";

import * as React from "react";
import { RiArrowRightLine, RiCheckLine, RiMailLine } from "@remixicon/react";

import { cn } from "@/utils/cn";
import * as Button from "@/components/ui/button";
import * as Input from "@/components/ui/input";

const STORAGE_KEY = "tempo.waitlist.email";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function getSnapshot(): string | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value && EMAIL_RE.test(value) ? value : null;
  } catch {
    return null;
  }
}

function getServerSnapshot(): string | null {
  return null;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

export function WaitlistForm({
  className,
  placeholder = "you@studio.com",
  ctaLabel = "Join the waitlist",
}: {
  className?: string;
  placeholder?: string;
  ctaLabel?: string;
}) {
  const storedEmail = React.useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );
  const uid = React.useId();
  const emailId = `waitlist-email-${uid}`;
  const errorId = `waitlist-error-${uid}`;
  const [email, setEmail] = React.useState("");
  const [justSaved, setJustSaved] = React.useState<string | null>(null);
  const [dismissed, setDismissed] = React.useState(false);
  const [invalid, setInvalid] = React.useState(false);

  const savedEmail = dismissed ? null : (justSaved ?? storedEmail);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = email.trim();
    if (!EMAIL_RE.test(value)) {
      setInvalid(true);
      return;
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, value);
    } catch {
      /* storage unavailable — still show success for this session */
    }
    setJustSaved(value);
    setDismissed(false);
    setInvalid(false);
  }

  function handleDismiss() {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* storage unavailable */
    }
    setJustSaved(null);
    setDismissed(true);
    setEmail("");
  }

  if (savedEmail) {
    return (
      <div
        className={cn(
          "flex flex-col gap-3 rounded-10 bg-bg-white-0 p-5 ring-1 ring-inset ring-stroke-soft-200",
          className,
        )}
      >
        <div className="flex items-center gap-3">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-tag-green-bg text-tag-green-fg">
            <RiCheckLine className="size-4" aria-hidden="true" />
          </span>
          <div>
            <p className="text-label-lg text-text-strong-950">
              You&rsquo;re on the list.
            </p>
            <p className="text-paragraph-sm text-text-sub-600">
              We&rsquo;ll email {savedEmail} when your invite opens.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleDismiss}
          className="self-start text-label-sm text-text-sub-600 underline-offset-4 transition-colors hover:text-text-strong-950 hover:underline"
        >
          Use a different address
        </button>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className={cn(
        "flex w-full flex-col gap-3 sm:flex-row sm:items-start",
        className,
      )}
    >
      <div className="flex-1">
        <label htmlFor={emailId} className="sr-only">
          Email address
        </label>
        <Input.Root>
          <Input.Wrapper
            className={cn(invalid && "ring-error-base focus-within:ring-error-base")}
          >
            <Input.Icon as={RiMailLine} />
            <Input.Input
              id={emailId}
              name="email"
              type="email"
              autoComplete="email"
              placeholder={placeholder}
              value={email}
              aria-invalid={invalid}
              aria-describedby={invalid ? errorId : undefined}
              onChange={(event) => {
                setEmail(event.target.value);
                if (invalid) setInvalid(false);
              }}
            />
          </Input.Wrapper>
        </Input.Root>
        <p
          id={errorId}
          role="alert"
          className={cn(
            "h-5 text-label-sm text-error-base transition-opacity",
            invalid ? "opacity-100" : "opacity-0",
          )}
        >
          {invalid ? "Enter a valid email address." : ""}
        </p>
      </div>
      <Button.Root type="submit" variant="neutral" mode="filled">
        {ctaLabel}
        <Button.Icon as={RiArrowRightLine} />
      </Button.Root>
    </form>
  );
}

