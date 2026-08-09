export function isNonEmptyString(value) {
    return typeof value === "string" && value.trim().length > 0;
}
export function validateSemanticIdentity(value) {
    if (!isNonEmptyString(value)) {
        throw new TypeError("options.semantic must be a non-empty absolute URI");
    }
    try {
        // Validation only: exact lexical identity is intentionally preserved.
        new URL(value);
    }
    catch {
        throw new TypeError("options.semantic must be a non-empty absolute URI");
    }
    return value;
}
export function contextFromAssertedValue(value) {
    if (!isNonEmptyString(value)) {
        return undefined;
    }
    try {
        new URL(value);
        return { kind: "uri", value };
    }
    catch {
        return { kind: "carrier-local", value };
    }
}
export function validateContext(value) {
    if ((value.kind !== "uri" && value.kind !== "carrier-local") ||
        !isNonEmptyString(value.value)) {
        return undefined;
    }
    if (value.kind === "uri") {
        try {
            new URL(value.value);
        }
        catch {
            return undefined;
        }
    }
    return { kind: value.kind, value: value.value };
}
export function copySource(value) {
    if (typeof value !== "object" || value === null) {
        return undefined;
    }
    const locator = Reflect.get(value, "locator");
    return isNonEmptyString(locator) ? { locator } : undefined;
}
export function result(semantic, carrier, context, affordance, source) {
    const copiedSource = copySource(source);
    return copiedSource === undefined
        ? { semantic, carrier, context, affordance }
        : { semantic, carrier, context, affordance, source: copiedSource };
}
//# sourceMappingURL=common.js.map