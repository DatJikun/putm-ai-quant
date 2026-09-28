import path from "path"

export function packsRoot() {
  return path.join(process.cwd(), "packs")
}

/**
 * Folder of one pack under `packs/`, or null when `id` is not a plain folder name.
 * Separators, `.`, `..` and NUL are refused so a request cannot leave `packs/`.
 */
export function resolvePackDir(id: string | null | undefined): string | null {
  if (!id || id === "." || id === ".." || id.includes("\0") || id !== path.basename(id)) {
    return null
  }
  const root = packsRoot()
  const dir = path.resolve(root, id)
  return path.dirname(dir) === root ? dir : null
}
