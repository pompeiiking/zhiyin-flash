/** Version endpoints are ordered ascending; every page must read the same latest row. */
export function latestAssetVersion<T extends { version: number }>(versions: readonly T[] | null | undefined): T | undefined {
  return versions?.slice().sort((a, b) => b.version - a.version)[0]
}
