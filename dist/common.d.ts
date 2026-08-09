import type { AppealAffordance, CarrierKind, ContextRef, SourceMetadata } from "./types.js";
export declare function isNonEmptyString(value: unknown): value is string;
export declare function validateSemanticIdentity(value: string): string;
export declare function contextFromAssertedValue(value: unknown): ContextRef | undefined;
export declare function validateContext(value: ContextRef): ContextRef | undefined;
export declare function copySource(value: unknown): SourceMetadata | undefined;
export declare function result(semantic: string, carrier: CarrierKind, context: ContextRef, affordance: AppealAffordance["affordance"], source: unknown): AppealAffordance;
//# sourceMappingURL=common.d.ts.map