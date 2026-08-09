import { result } from "../common.js";
const TOKEN = /^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$/u;
const REGISTERED_RELATION = /^[a-z][a-z0-9.-]*$/u;
function isRelationType(value) {
    if (REGISTERED_RELATION.test(value))
        return true;
    try {
        new URL(value);
        return true;
    }
    catch {
        return false;
    }
}
function splitDelimited(input, delimiter, trackAngles) {
    const parts = [];
    let start = 0;
    let quoted = false;
    let escaped = false;
    let inAngle = false;
    for (let index = 0; index < input.length; index += 1) {
        const character = input[index];
        if (quoted) {
            if (escaped) {
                escaped = false;
            }
            else if (character === "\\") {
                escaped = true;
            }
            else if (character === '"') {
                quoted = false;
            }
            continue;
        }
        if (character === '"') {
            quoted = true;
        }
        else if (trackAngles && character === "<") {
            if (inAngle)
                return undefined;
            inAngle = true;
        }
        else if (trackAngles && character === ">") {
            if (!inAngle)
                return undefined;
            inAngle = false;
        }
        else if (character === delimiter && !inAngle) {
            parts.push(input.slice(start, index));
            start = index + 1;
        }
    }
    if (quoted || escaped || inAngle)
        return undefined;
    parts.push(input.slice(start));
    return parts;
}
function decodeParameterValue(raw) {
    const value = raw.trim();
    if (!value.startsWith('"')) {
        return TOKEN.test(value) ? value : undefined;
    }
    if (value.length < 2 || !value.endsWith('"'))
        return undefined;
    let decoded = "";
    let escaped = false;
    for (let index = 1; index < value.length - 1; index += 1) {
        const character = value[index];
        if (escaped) {
            decoded += character;
            escaped = false;
        }
        else if (character === "\\") {
            escaped = true;
        }
        else if (character === '"') {
            return undefined;
        }
        else {
            decoded += character;
        }
    }
    return escaped ? undefined : decoded;
}
function parseLinkValue(value) {
    const trimmed = value.trim();
    if (!trimmed.startsWith("<"))
        return undefined;
    const targetEnd = trimmed.indexOf(">");
    if (targetEnd < 1)
        return undefined;
    const target = trimmed.slice(1, targetEnd);
    const rest = trimmed.slice(targetEnd + 1);
    if (rest.trim().length > 0 && !rest.trimStart().startsWith(";")) {
        return undefined;
    }
    const segments = splitDelimited(rest, ";", false);
    if (segments === undefined)
        return undefined;
    let relations;
    let anchor;
    for (const rawSegment of segments.slice(1)) {
        const segment = rawSegment.trim();
        if (segment.length === 0)
            return undefined;
        const equals = segment.indexOf("=");
        if (equals < 1)
            return undefined;
        const name = segment.slice(0, equals).trim().toLowerCase();
        if (!TOKEN.test(name))
            return undefined;
        const parameterValue = decodeParameterValue(segment.slice(equals + 1));
        if (parameterValue === undefined)
            return undefined;
        if (name === "rel") {
            if (relations !== undefined)
                return undefined;
            relations = parameterValue.split(/ +/u);
            if (relations.length === 0 ||
                relations.some((relation) => !isRelationType(relation))) {
                return undefined;
            }
        }
        else if (name === "anchor") {
            if (anchor !== undefined)
                return undefined;
            anchor = parameterValue;
        }
    }
    return relations === undefined ? undefined : { target, relations, ...(anchor === undefined ? {} : { anchor }) };
}
function absolute(reference, base) {
    try {
        return new URL(reference, base).href;
    }
    catch {
        return undefined;
    }
}
function extensionRelationEquals(left, right) {
    // RFC 8288 section 2.1.1 requires extension relation URI comparison to be
    // case-insensitive, character by character.
    if (left.length !== right.length)
        return false;
    for (let index = 0; index < left.length; index += 1) {
        const leftCode = left.charCodeAt(index);
        const rightCode = right.charCodeAt(index);
        const foldedLeft = leftCode >= 65 && leftCode <= 90 ? leftCode + 32 : leftCode;
        const foldedRight = rightCode >= 65 && rightCode <= 90 ? rightCode + 32 : rightCode;
        if (foldedLeft !== foldedRight)
            return false;
    }
    return true;
}
/**
 * Parses a fail-closed RFC 8288 subset: angle-bracket targets, quoted or token
 * parameters, `rel`, and at most one `anchor`. Malformed values are omitted.
 */
export function discoverRfc8288(input, semantic) {
    const representationUrl = absolute(input.representationUrl, input.representationUrl);
    if (representationUrl === undefined)
        return [];
    const discovered = [];
    for (const header of input.linkHeaders) {
        const values = splitDelimited(header, ",", true);
        if (values === undefined)
            continue;
        for (const value of values) {
            const link = parseLinkValue(value);
            if (link === undefined ||
                !link.relations.some((relation) => extensionRelationEquals(relation, semantic))) {
                continue;
            }
            const target = absolute(link.target, representationUrl);
            const context = link.anchor === undefined
                ? representationUrl
                : absolute(link.anchor, representationUrl);
            if (target === undefined || context === undefined)
                continue;
            discovered.push(result(semantic, "rfc8288", { kind: "uri", value: context }, { kind: "link", target }, input.source));
        }
    }
    return discovered;
}
//# sourceMappingURL=rfc8288.js.map