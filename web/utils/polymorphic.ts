import * as React from "react";

export type PolymorphicRef<C extends React.ElementType> =
  React.ComponentPropsWithRef<C>["ref"];

export type PolymorphicComponentProps<
  C extends React.ElementType,
  Props = Record<never, never>,
> = Omit<React.ComponentPropsWithoutRef<C>, "as" | keyof Props> &
  Props & { as?: C };
