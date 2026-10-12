package com.fis.noco.views;

import com.vaadin.flow.component.dependency.CssImport;
import com.vaadin.flow.component.dependency.NpmPackage;
import com.vaadin.flow.component.html.Span;

import java.util.Map;

/**
 * A nation shown as its flag, optionally followed by the FIS code.
 *
 * Flags come from the flag-icons package (SVG, bundled with the app).  It is
 * keyed by ISO 3166 alpha-2 codes, while FIS prints its own three-letter
 * codes — hence the table below.  A code without an entry there ("FIS" for
 * officials, a nation not listed yet) is shown as plain text.
 */
@NpmPackage(value = "flag-icons", version = "7.5.0")
@CssImport("flag-icons/css/flag-icons.min.css")
public class NationFlag extends Span {

    private static final Map<String, String> ISO_BY_FIS = Map.ofEntries(
            Map.entry("AND", "ad"), Map.entry("ARG", "ar"), Map.entry("ARM", "am"), Map.entry("AUS", "au"),
            Map.entry("AUT", "at"), Map.entry("BEL", "be"), Map.entry("BIH", "ba"), Map.entry("BLR", "by"),
            Map.entry("BUL", "bg"), Map.entry("CAN", "ca"), Map.entry("CHI", "cl"), Map.entry("CHN", "cn"),
            Map.entry("CRO", "hr"), Map.entry("CZE", "cz"), Map.entry("DEN", "dk"), Map.entry("ESP", "es"),
            Map.entry("EST", "ee"), Map.entry("FIN", "fi"), Map.entry("FRA", "fr"), Map.entry("GBR", "gb"),
            Map.entry("GEO", "ge"), Map.entry("GER", "de"), Map.entry("GRE", "gr"), Map.entry("HUN", "hu"),
            Map.entry("IRL", "ie"), Map.entry("ISL", "is"), Map.entry("ITA", "it"), Map.entry("JPN", "jp"),
            Map.entry("KAZ", "kz"), Map.entry("KGZ", "kg"), Map.entry("KOR", "kr"), Map.entry("LAT", "lv"),
            Map.entry("LIE", "li"), Map.entry("LTU", "lt"), Map.entry("LUX", "lu"), Map.entry("MDA", "md"),
            Map.entry("MGL", "mn"), Map.entry("MKD", "mk"), Map.entry("NED", "nl"), Map.entry("NOR", "no"),
            Map.entry("NZL", "nz"), Map.entry("POL", "pl"), Map.entry("POR", "pt"), Map.entry("ROU", "ro"),
            Map.entry("RUS", "ru"), Map.entry("SLO", "si"), Map.entry("SRB", "rs"), Map.entry("SUI", "ch"),
            Map.entry("SVK", "sk"), Map.entry("SWE", "se"), Map.entry("THA", "th"), Map.entry("TUR", "tr"),
            Map.entry("UKR", "ua"), Map.entry("USA", "us"), Map.entry("UZB", "uz"));

    /** Flag followed by the code — for tables, where similar flags are hard to tell apart. */
    public NationFlag(String fisCode) {
        this(fisCode, true);
    }

    /** With {@code showCode = false} only the flag is shown; the code is its tooltip. */
    public NationFlag(String fisCode, boolean showCode) {
        String code = fisCode == null ? "" : fisCode.trim().toUpperCase();
        String iso = ISO_BY_FIS.get(code);
        getStyle().set("display", "inline-flex").set("align-items", "center")
                .set("gap", "0.4em").set("white-space", "nowrap");

        if (iso == null) {
            setText(code);
            return;
        }
        Span flag = new Span();
        flag.addClassNames("fi", "fi-" + iso);
        // A thin outline keeps white stripes (JPN, FIN, POL) visible on a white page
        flag.getStyle().set("box-shadow", "0 0 0 1px var(--lumo-contrast-20pct)").set("flex-shrink", "0");
        flag.getElement().setAttribute("title", code);
        flag.getElement().setAttribute("role", "img");
        flag.getElement().setAttribute("aria-label", code);
        add(flag);
        if (showCode) {
            add(new Span(code));
        }
    }
}
