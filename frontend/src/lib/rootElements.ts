// Determines which global elements are document roots to render at the top
// level of the diagram and tree.
//
// The parser merges the top-level <xs:element> declarations of the main file
// AND every <xs:include>/<xs:import>ed file into one flat ``model.elements``
// list. Rendering all of them as roots is noisy: an included schema's globals
// (e.g. the ~24 globals of xmldsig-core-schema.xsd behind FundsXML) show up as
// peers of the real root. We therefore keep only the globals declared in the
// main file — the file the user actually loaded. Included declarations remain
// in the model (and are still reachable by reference), they just don't appear
// as standalone roots.

import type { ElementDecl, SchemaModel } from "../types/schema";

export function computeRootElements(model: SchemaModel): ElementDecl[] {
  // ``model.files`` marks exactly one source file as "main" (the loaded
  // entry point). Match elements back to it via their source_ref.file_id.
  const mainFileId = model.files.find((f) => f.relationship === "main")?.id;
  if (mainFileId == null) return model.elements;

  const roots = model.elements.filter(
    (el) => el.source_ref?.file_id === mainFileId,
  );

  // Safeguard: a main file that declares no globals of its own (a pure
  // include/import aggregator) would leave nothing to show — fall back to the
  // full list so the views are never empty.
  return roots.length > 0 ? roots : model.elements;
}
