// AlignUI Input, Tempo palette
import * as React from "react";
import { RiSearchLine } from "@remixicon/react";

import { cn } from "@/utils/cn";
import { tv, type VariantProps } from "@/utils/tv";

const inputVariants = tv({
  slots: {
    root: "flex w-full flex-col gap-1.5",
    wrapper: [
      "relative flex items-center gap-2 rounded-10 bg-bg-white-0 px-3.5",
      "ring-1 ring-inset ring-stroke-soft-200 transition duration-200",
      "focus-within:ring-2 focus-within:ring-primary-base",
    ],
    input: [
      "h-11 w-full bg-transparent text-paragraph-md text-text-strong-950",
      "placeholder:text-text-soft-400 outline-none",
    ],
    icon: "size-5 shrink-0 text-text-soft-400",
  },
  variants: {
    size: {
      medium: {},
    },
  },
  defaultVariants: {
    size: "medium",
  },
});

type InputSharedProps = VariantProps<typeof inputVariants>;

type InputRootProps = React.HTMLAttributes<HTMLDivElement> & InputSharedProps;

const InputRoot = React.forwardRef<HTMLDivElement, InputRootProps>(
  ({ className, children, ...rest }, forwardedRef) => {
    const { root } = inputVariants();
    return (
      <div ref={forwardedRef} className={root({ class: className })} {...rest}>
        {children}
      </div>
    );
  },
);
InputRoot.displayName = "InputRoot";

function InputWrapper({
  className,
  children,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  const { wrapper } = inputVariants();
  return (
    <div className={wrapper({ class: className })} {...rest}>
      {children}
    </div>
  );
}
InputWrapper.displayName = "InputWrapper";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...rest }, forwardedRef) => {
    const { input } = inputVariants();
    return <input ref={forwardedRef} className={input({ class: className })} {...rest} />;
  },
);
Input.displayName = "Input";

function InputIcon({
  as,
  className,
  ...rest
}: React.SVGProps<SVGSVGElement> & { as?: React.ElementType }) {
  const { icon } = inputVariants();
  const Component = as || RiSearchLine;
  return <Component className={icon({ class: className })} {...rest} />;
}
InputIcon.displayName = "InputIcon";

export { InputRoot as Root, InputWrapper as Wrapper, Input, InputIcon as Icon, cn };
