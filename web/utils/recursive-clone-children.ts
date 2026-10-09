import * as React from "react";

type ClonableElement = React.ReactElement<Record<string, unknown>>;

function isElementWithDisplayName(
  element: React.ReactElement,
  displayNames: string[],
): boolean {
  return displayNames.includes(
    (element.type as { displayName?: string } | undefined)?.displayName ?? "",
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

    const element = child as ClonableElement;
    const childProps: Record<string, unknown> = { ...props };

    if (element.props.id) {
      childProps.id = element.props.id;
    } else if (uniqueId) {
      childProps.id = uniqueId;
    }

    const cloned = React.cloneElement(element, childProps) as ClonableElement;

    if (
      isElementWithDisplayName(cloned, displayNames) &&
      React.isValidElement(cloned.props.children)
    ) {
      return React.cloneElement(cloned, {
        children: recursiveCloneChildren(
          cloned.props.children as React.ReactNode,
          props,
          displayNames,
          uniqueId,
          asChild,
        ),
      });
    }

    return cloned;
  });
}
