type QkPart = string | number | Record<string, unknown>;

export function qk(resource: string, ...parts: QkPart[]): readonly unknown[] {
  return [resource, ...parts];
}
