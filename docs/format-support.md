# ALTO / PAGE version support matrix

What saknussemm accepts, what it writes back, and what it can check
against an official schema. "Parse/rewrite" is
namespace-tolerant: the parsers accept any root namespace matching the
format marker (`loc.gov/standards/alto` / `primaresearch.org/PAGE`) and
the rewriter re-emits the document in its ORIGINAL namespace. "XSD
bundled" means `saknussemm.formats.validation` can validate that
namespace offline (schemas + provenance: `../src/saknussemm/formats/xsd/`).

| Format | Root namespace | Parse / rewrite | XSD bundled |
|---|---|---|---|
| ALTO v2 | `http://www.loc.gov/standards/alto/ns-v2#` | yes | `alto-2-1.xsd` |
| ALTO v3 | `http://www.loc.gov/standards/alto/ns-v3#` | yes | `alto-3-1.xsd` |
| ALTO v4 | `http://www.loc.gov/standards/alto/ns-v4#` | yes | `alto-4-4.xsd` |
| PAGE 2013 | `…/PAGE/gts/pagecontent/2013-07-15` | yes | `pagecontent_2013-07-15.xsd` |
| PAGE 2019 | `…/PAGE/gts/pagecontent/2019-07-15` | yes | `pagecontent_2019-07-15.xsd` |
| PAGE 2024 | `…/PAGE/gts/pagecontent/2024-07-15` | yes | `pagecontent_2024-07-15.xsd` |
| PAGE, other dates | any other `pagecontent/…` namespace | yes (tolerant) | no — validation raises `ParseError` |

## Validation roles

- **Input — diagnostic.** Real-world exports carry dialect extensions:
  Transkribus writes a `TranskribusMetadata` element that the official
  2013-07-15 schema does not know (pinned by
  `tests/test_xsd_validation.py`). A host should SURFACE input
  violations, not refuse the document — the manifest builds fine.
- **Output — runtime gate.** The pipeline checks the serialized XML before
  delivering it: same root and TextLine inventory, and line readings equal
  to those reported by the adapter and accepted by the engine. For bundled
  namespaces it also compares XSD diagnostics against the source: a valid
  source requires a valid output; existing dialect messages are tolerated
  only up to their original occurrence count. This compares diagnostics,
  not the location of each pre-existing defect. A schema error can also
  prevent libxml from validating the remainder of a subtree: unchanged
  diagnostics do not prove that this subtree stayed conformant. Rejected
  files appear in `undeliverable_files`; `write()` refuses an incomplete
  result by default.
  Validation is offline. Namespaces without a bundled schema still receive
  the XML/text checks, but **no XSD guarantee**. Direct low-level rewriter
  calls do not run this pipeline gate.

For a production workflow requiring full schema conformance, require
`validate_bytes(output) == []` on every candidate before ingestion and use
only namespaces with a bundled schema. A tolerant dialect round-trip is
an explicit exception for the host to review, not a schema certification.
Even full XSD validity does not establish text accuracy or correct boxes.

## Source stability

Parsers hash the same bytes they parse. At run startup the pipeline captures
each source in memory and compares it to the parser's digest before any
producer call. Built-in ALTO/PAGE adapters render that capture, even if the
original path changes or disappears during correction. This retains one
copy of all source bytes for the run and adds output parsing/validation work.

The public `FormatAdapter` remains path-based. Custom adapters and subclasses
are still invoked; their paths are checked against the capture before and
after rewriting. A detected change withholds the file. These checks are not
an immutable input guarantee for arbitrary custom code: hosts must keep its
source paths stable. For host-defined XML formats, extraction and structural
validation remain the custom adapter's responsibility; the pipeline checks
well-formed XML, the root and the adapter's declared texts against decisions.

## API

```python
from saknussemm.formats.validation import validate_file, validate_bytes

violations = validate_file(Path("scan.xml"))   # [] == valid
violations = validate_bytes(xml_bytes, source_name="scan.xml")
```

Both raise `ParseError` (classified, §8.4) for malformed XML or a root
namespace with no bundled schema.

## Ce que les schémas embarqués coûtent, et pourquoi ils restent

Les sept XSD pèsent **380 Ko décompressés, soit 32 % du contenu du wheel** —
qui fait 363 Ko compressés au total. Ils sont dans l'installation de BASE, pas
derrière un extra, et c'est une décision plutôt qu'un oubli :

- la validation hors-ligne n'a de sens que si elle est hors-ligne. Un extra
  qui téléchargerait les schémas au premier appel rendrait le module
  dépendant du réseau exactement là où son intérêt est de ne pas l'être ;
- un extra `pip` ajoute des DÉPENDANCES, pas des fichiers. Sortir les schémas
  du wheel demanderait une seconde distribution, soit une unité de
  publication de plus à versionner et à garder cohérente, pour 380 Ko ;
- `saknussemm.formats.validation` n'est pas réexporté au niveau du paquet
  (la surface publique est close, cf. `versioning.md`), mais il est
  documenté ici et importable par son chemin de module, ce que
  `versioning.md` décrit comme une porte supportée.

`tests/test_packaging_excludes_corpora.py` vérifie que le wheel CONSTRUIT
porte bien les sept schémas : `test_xsd_validation.py` s'exécute depuis
l'arbre source et passerait à l'identique sur un wheel qui les aurait
perdus.
