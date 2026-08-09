import { isNonEmptyString, result, validateContext } from "../common.js";
import type { AppealAffordance, InlineTestInput } from "../types.js";

/**
 * Non-normative normalized test carrier. It intentionally does not model
 * methods, forms, eligibility, deadlines, trust, or execution.
 */
export function discoverInlineTest(
  input: InlineTestInput,
  semantic: string,
): AppealAffordance[] {
  const context = validateContext(input.context);
  if (context === undefined) return [];

  const idCounts = new Map<string, number>();
  for (const action of input.actions) {
    if (isNonEmptyString(action.id)) {
      idCounts.set(action.id, (idCounts.get(action.id) ?? 0) + 1);
    }
  }

  const discovered: AppealAffordance[] = [];
  for (const action of input.actions) {
    if (
      !isNonEmptyString(action.id) ||
      idCounts.get(action.id) !== 1 ||
      action.semantic !== semantic
    ) {
      continue;
    }

    discovered.push(
      result(
        semantic,
        "inline-test",
        context,
        { kind: "inline-action", actionId: action.id },
        input.source,
      ),
    );
  }

  return discovered;
}
