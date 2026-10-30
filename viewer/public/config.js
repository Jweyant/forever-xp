// Must load before the vendor scripts: they only set these globals when nothing has.
// All model files come through this origin's /zam/ proxy (see src/index.js). The vendor's other
// global (WOTLK_TO_RETAIL_DISPLAY_ID_API) keeps its default: our flow never calls it, and the
// page's CSP (connect-src 'self') blocks that host anyway.
window.CONTENT_PATH = "/zam/modelviewer/classic/";
