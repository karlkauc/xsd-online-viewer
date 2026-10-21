import { FREEXMLTOOLKIT_GO, ODATA_VIEWER_GO, TPT_CONVERTER_GO, XML_VIEWER_GO, XSD_VIEWER_GO } from "../lib/links";

// Identical on all sites of the family (and in backend/app/content/site.py
// for the server-rendered pages); only SELF differs.
const SELF = "xsd";

const FAMILY = [
  { key: "xsd", label: "XSD Viewer", href: XSD_VIEWER_GO },
  { key: "xml", label: "XML Viewer", href: XML_VIEWER_GO },
  { key: "odata", label: "OData Viewer", href: ODATA_VIEWER_GO },
  { key: "tpt", label: "TPT Converter", href: TPT_CONVERTER_GO },
  { key: "desktop", label: "Desktop app", href: FREEXMLTOOLKIT_GO },
] as const;

/** "Part of the FreeXmlToolkit family" line with links to the sibling tools. */
export function FamilyFooter({ className }: { className?: string }) {
  return (
    <p className={className}>
      Part of the FreeXmlToolkit family:{" "}
      {FAMILY.map((item, i) => (
        <span key={item.key}>
          {i > 0 && " · "}
          {item.key === SELF ? (
            <strong className="font-medium" aria-current="page">
              {item.label}
            </strong>
          ) : (
            <a className="underline" href={item.href} target="_blank" rel="noopener noreferrer">
              {item.label}
            </a>
          )}
        </span>
      ))}
      . Free, open source, no account, no ads.{" "}
      <a className="underline" href="/guides">
        Guides and resources
      </a>
    </p>
  );
}
