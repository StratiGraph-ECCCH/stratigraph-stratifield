# Sphinx configuration — stratigraph-stratifield
#
# The same as stratigraph-server's docs/conf.py (19 November 2026), with the
# names changed: theme, MyST, version read from pyproject, LaTeX with XeLaTeX
# and DejaVu, and the pass that sends a link leaving docs/ to GitHub. The
# documents are markdown read by MyST, and there is no autodoc: StratiField's
# manual, like the server's, is prose.
#
# The gate is `sphinx-build -W docs docs/_build`: a warning is an error.

import datetime
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# -- Project ----------------------------------------------------------------
project = 'StratiField'
copyright = f'2026-{datetime.datetime.now().year}, Consiglio Nazionale delle Ricerche (CNR) — Istituto di Scienze del Patrimonio Culturale'
author = 'Emanuel Demetrescu'


def _read_version():
    """StratiField's version, never typed here: from pyproject.toml."""
    with open(os.path.join(ROOT, 'pyproject.toml'), encoding='utf-8') as fh:
        m = re.search(r'^version\s*=\s*"([^"]+)"', fh.read(), re.MULTILINE)
    if not m:
        raise RuntimeError('version not found in pyproject.toml')
    return m.group(1)


release = _read_version()
version = '.'.join(release.split('.')[:2])

# -- Extensions -------------------------------------------------------------
extensions = ['myst_parser']

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
master_doc = 'index'
source_suffix = {'.md': 'markdown'}
language = 'en'

# -- MyST -------------------------------------------------------------------
myst_enable_extensions = ['deflist', 'colon_fence', 'linkify']
myst_heading_anchors = 3


# -- HTML -------------------------------------------------------------------
html_theme = 'sphinx_rtd_theme'
templates_path = ['_templates']
html_static_path = ['_static']

# Il marchio, vendorizzato da `stratigraph-brand` con il suo
# `docs-theme/sync-brand-docs.sh`, come lo vendorizzano le applicazioni: un
# manuale letto in trincea non ha una CDN. Chiaro e scuro seguono
# l'impostazione di sistema di chi legge; i contrasti sono misurati nel
# marchio. Per cambiare un colore si cambia lì, e si ridà il sync.
# EPUB non conosce il tipo di un .woff2 e, con -W, la sua lamentela
# («unknown mimetype … ignoring») ferma la pubblicazione: i caratteri del
# marchio servono alla pagina web, non al libro.
suppress_warnings = ['epub.unknown_project_files']

html_css_files = [
    'brand/stratigraph-theme.css',
    'brand/sphinx-rtd-bridge.css',
]
# L'interruttore delle due facce: chiaro, scuro, come il sistema. Senza
# scelta esplicita vale il sistema di chi legge, che è il modo di serie.
html_js_files = ['brand/brand-theme-toggle.js']

html_theme_options = {
    'prev_next_buttons_location': 'bottom',
    'collapse_navigation': True,
    'sticky_navigation': True,
    'navigation_depth': 3,
    'titles_only': False,
}
html_context = {
    'display_github': True,
    'github_user': 'StratiGraph-ECCCH',
    'github_repo': 'stratigraph-stratifield',
    'github_version': 'main',
    'conf_py_path': '/docs/',
}
html_last_updated_fmt = '%d %b %Y'

# -- LaTeX / PDF (as in s3Dgraphy and stratigraph-templates) ----------------
latex_engine = 'xelatex'
latex_use_xindy = False
latex_elements = {
    'papersize': 'a4paper',
    'pointsize': '10pt',
    'figure_align': 'htbp',
    'fontpkg': r"""
\IfFontExistsTF{DejaVu Serif}
  {\setmainfont{DejaVu Serif}}
  {\IfFontExistsTF{FreeSerif}{\setmainfont{FreeSerif}}{}}
\IfFontExistsTF{DejaVu Sans}
  {\setsansfont{DejaVu Sans}}
  {\IfFontExistsTF{FreeSans}{\setsansfont{FreeSans}}{}}
\IfFontExistsTF{DejaVu Sans Mono}
  {\setmonofont{DejaVu Sans Mono}[Scale=MatchLowercase]}
  {\IfFontExistsTF{FreeMono}{\setmonofont{FreeMono}[Scale=MatchLowercase]}{}}
""",
    'preamble': r"""
\sloppy
""",
}
latex_documents = [
    ('index', 'stratifield.tex', 'StratiField',
     'Emanuel Demetrescu', 'manual'),
]
latex_show_urls = 'footnote'

# -- Links that leave docs/ -------------------------------------------------
# The documents were written to be read in the repository, so they link to
# files beside them as files: `../../stratigraph-server/docs/DEPLOYMENT.md`.
# On the site those are not pages. Rather than rewriting the documents, this
# pass reads each such link against the FILE that contains it and sends it to
# GitHub: a file of this repository to its blob, a sibling repository to its
# home. Siblings are matched by NAME, not on disk — on Read the Docs only this
# repository is checked out. A link this pass does not understand is left to
# MyST, which warns, and `-W` makes the warning an error.
_THIS = 'https://github.com/StratiGraph-ECCCH/stratigraph-stratifield'
_SIBLINGS = {
    's3Dgraphy': 'https://github.com/ExtendedMatrix/s3Dgraphy',
    'EMStudio': 'https://github.com/ExtendedMatrix/EMStudio',
    'EM-blender-tools': 'https://github.com/zalmoxes-laran/EM-blender-tools',
    'stratigraph-catalog': 'https://github.com/StratiGraph-ECCCH/stratigraph-catalog',
    'stratigraph-templates': 'https://github.com/StratiGraph-ECCCH/stratigraph-templates',
    'stratigraph-server': 'https://github.com/StratiGraph-ECCCH/stratigraph-server',
    'heriverse-ansible': 'https://github.com/StratiGraph-ECCCH/heriverse-ansible',
}

from sphinx.transforms.post_transforms import SphinxPostTransform  # noqa: E402


def _outside_uri(raw, source_file):
    """The GitHub address of a link that leaves docs/, or None."""
    if not raw or '://' in raw or raw.startswith('#'):
        return None
    path, _, anchor = raw.partition('#')
    here = os.path.dirname(source_file)
    full = os.path.normpath(path if os.path.isabs(path) else os.path.join(here, path))
    parent = os.path.dirname(ROOT)
    if full == ROOT or full.startswith(ROOT + os.sep):
        rel = os.path.relpath(full, ROOT).replace(os.sep, '/')
        if rel == 'docs' or rel.startswith('docs/'):
            return None                       # a page of the site: MyST's
        for cand in (full, full + '.md'):
            if os.path.isfile(cand):
                rel = os.path.relpath(cand, ROOT).replace(os.sep, '/')
                return f'{_THIS}/blob/HEAD/{rel}' + (f'#{anchor}' if anchor else '')
        if os.path.isdir(full):
            return _THIS if rel == '.' else f'{_THIS}/tree/HEAD/{rel}'
        return None
    if full.startswith(parent + os.sep):
        name, _, rest = os.path.relpath(full, parent).replace(os.sep, '/').partition('/')
        home = _SIBLINGS.get(name)
        if home is None:
            return None
        if not rest:
            return home
        if not os.path.splitext(rest)[1]:
            rest += '.md'                     # MyST dropped the suffix
        # Where the sibling IS checked out beside this one (a local build, not
        # Read the Docs), a link to a file it does not have is a broken link:
        # left to MyST, which warns, and `-W` stops. The manual's two parts
        # point into StratiField's docs, and a page moved there must not leave
        # a link behind that only GitHub would find broken.
        sibling = os.path.join(parent, name)
        if os.path.isdir(sibling) and not os.path.exists(os.path.join(sibling, rest)):
            return None
        return f'{home}/blob/HEAD/{rest}' + (f'#{anchor}' if anchor else '')
    return None


class OutsideLinks(SphinxPostTransform):
    default_priority = 8          # before MystReferenceResolver (9)

    def run(self, **kwargs):
        from docutils import nodes
        from sphinx import addnodes
        for node in list(self.document.findall(addnodes.pending_xref)):
            if node.get('reftype') != 'myst':
                continue
            source = node.source or self.env.doc2path(self.env.docname)
            uri = _outside_uri(node.get('reftarget') or '', str(source))
            if uri is None:
                continue
            ref = nodes.reference('', '', internal=False, refuri=uri)
            ref += node.children
            node.replace_self(ref)


def setup(app):
    app.add_post_transform(OutsideLinks)
