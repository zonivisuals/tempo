import * as React from "react";

type AnyElement = React.ReactElement<any>;

function isElementWithDisplayName(
  element: AnyElement,
  displayNames: string[],
): boolean {
  return displayNames.includes(
    (element.type as any)?.displayName ?? "",
  );
}

export function recursiveCloneChildren(
  children: React.ReactNode,
  props: Record<string, unknown>,
  displayNames: string[],
  uniqueId?: string,
  asChild?: boolean,
): React.ReactNode {
  if (asChild) return children;

  return React.Children.map(children, (child) => {
    if (!React.isValidElement(child)) return child;

    const element = child as AnyElement;
    const childProps: Record<string, unknown> = { ...props };

    if (element.props.id) {
      childProps.id = element.props.id;
    } else if (uniqueId) {
      childProps.id = uniqueId;
    }

    const cloned = React.cloneElement(element, childProps);

    if (isElementWithDisplayName(cloned, displayNames) && cloned.props.children) {
      return React.cloneElement(cloned, {
        children: recursiveCloneChildren(
          cloned.props.children,
          props,
          displayNames,
          uniqueId,
          asChild,
        ),
      } as Partial<AnyElement["props"]>);
    }

    return cloned;
  });
}
