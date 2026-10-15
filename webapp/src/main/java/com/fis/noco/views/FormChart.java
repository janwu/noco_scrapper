package com.fis.noco.views;

import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.Competition;
import com.vaadin.flow.component.html.Div;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;

/**
 * Form over a season: the ranks of an athlete in every individual competition,
 * drawn as SVG on the server.
 *
 * <p>x: the competitions of the season in date order, also those the athlete did
 * not start (the line breaks there).  y: the rank, 1 at the top; a band marks the
 * podium.  Final rank, and optionally the rank of the jump and of the
 * cross-country race.  DNF / DNS / DSQ sit in a lane below the scale.  Hovering
 * a competition shows a crosshair and its ranks; a click opens it.</p>
 *
 * <p>Series colours: the first three slots of the reference categorical palette,
 * validated for colour-vision deficiency in light and dark mode; text, grid and
 * axes use the Lumo text colours.</p>
 */
final class FormChart {

    private FormChart() {
    }

    record Series(String key, String label, String color, Function<CombinedResult, Integer> rank) {
    }

    static final Series FINAL = new Series("final", "Rank", "var(--fc-s1)", CombinedResult::getRank);
    static final Series JUMP = new Series("jump", "Jump", "var(--fc-s2)", CombinedResult::getJumpRank);
    static final Series XC = new Series("xc", "XC", "var(--fc-s3)", CombinedResult::getXcRank);

    private static final int STEP = 34, LEFT = 46, RIGHT = 58, TOP = 12, PLOT = 240, LANE = 26, LABELS = 78;

    static Div create(List<Competition> competitions, Map<Long, CombinedResult> results, List<Series> series) {
        int n = competitions.size();
        int width = Math.max(640, LEFT + n * STEP + RIGHT);
        int laneY = TOP + PLOT + LANE / 2 + 6;
        int height = TOP + PLOT + LANE + LABELS;

        int worst = 10;
        for (Competition c : competitions) {
            CombinedResult r = results.get(c.getId());
            if (r == null) continue;
            for (Series s : series) {
                Integer v = s.rank().apply(r);
                if (v != null) worst = Math.max(worst, v);
            }
        }
        int yMax = Math.min(60, (int) Math.ceil(worst / 10.0) * 10);

        StringBuilder svg = new StringBuilder();
        svg.append(String.format(Locale.ROOT,
                "<svg class='fc-svg' viewBox='0 0 %d %d' width='%d' height='%d' role='img' aria-label='Ranks per competition'>",
                width, height, width, height));
        // podium band and grid
        svg.append(rect(LEFT, y(0.5, yMax), n * STEP, y(3.5, yMax) - y(0.5, yMax), "fill:var(--fc-band)"));
        for (int r = 0; r <= yMax; r += 10) {
            int rank = Math.max(1, r);
            double yy = y(rank, yMax);
            svg.append(String.format(Locale.ROOT,
                    "<line x1='%d' x2='%d' y1='%.1f' y2='%.1f' class='fc-grid'/>", LEFT, LEFT + n * STEP, yy, yy));
            svg.append(text(LEFT - 8, yy + 4, String.valueOf(rank), "end", "fc-axis"));
        }
        svg.append(text(LEFT - 8, laneY + 4, "DNF", "end", "fc-axis"));
        svg.append(String.format(Locale.ROOT, "<text x='12' y='%d' class='fc-axis' transform='rotate(-90 12 %d)' text-anchor='middle'>Rank</text>",
                TOP + PLOT / 2, TOP + PLOT / 2));

        // competitions: labels below, hit areas for hover
        for (int i = 0; i < n; i++) {
            Competition c = competitions.get(i);
            double x = x(i);
            String label = shortVenue(c.getDisplayLocation()) + " " + shortDate(c.getCompetitionDate());
            svg.append(String.format(Locale.ROOT,
                    "<text x='%.1f' y='%d' class='fc-axis' text-anchor='end' transform='rotate(-45 %.1f %d)'>%s</text>",
                    x + 4, TOP + PLOT + LANE + 12, x + 4, TOP + PLOT + LANE + 12, esc(label)));
        }
        svg.append(String.format(Locale.ROOT,
                "<line class='fc-cross' x1='0' x2='0' y1='%d' y2='%d' style='display:none'/>", TOP, TOP + PLOT + LANE));

        // lines (broken where the athlete did not start), then the markers; the final rank
        // is drawn last so that it stays on top where the lines meet
        List<Series> order = new ArrayList<>(series);
        java.util.Collections.reverse(order);
        List<double[]> ends = new ArrayList<>();
        List<String> endLabels = new ArrayList<>();
        for (Series s : order) {
            StringBuilder path = new StringBuilder();
            boolean open = false;
            double lastX = -1, lastY = -1;
            for (int i = 0; i < n; i++) {
                CombinedResult r = results.get(competitions.get(i).getId());
                Integer v = r == null ? null : s.rank().apply(r);
                if (v == null) {
                    open = false;
                    continue;
                }
                double xx = x(i), yy = y(Math.min(v, yMax), yMax);
                path.append(open ? " L" : " M").append(String.format(Locale.ROOT, "%.1f %.1f", xx, yy));
                open = true;
                lastX = xx;
                lastY = yy;
            }
            if (path.length() > 0) {
                svg.append(String.format("<path d='%s' class='fc-line' style='stroke:%s'/>", path.toString().trim(), s.color()));
                ends.add(new double[]{lastX, lastY});
                endLabels.add(s.label());
            }
        }
        // direct labels at the line ends, only where they do not collide (the legend names them anyway)
        for (int i = 0; i < ends.size(); i++) {
            boolean clear = true;
            for (int j = 0; j < ends.size(); j++) {
                if (i != j && Math.abs(ends.get(i)[0] - ends.get(j)[0]) < 40 && Math.abs(ends.get(i)[1] - ends.get(j)[1]) < 14) {
                    clear = false;
                }
            }
            if (clear && ends.size() > 1) {
                svg.append(text(ends.get(i)[0] + 9, ends.get(i)[1] + 4, endLabels.get(i), "start", "fc-label"));
            }
        }
        for (Series s : order) {
            for (int i = 0; i < n; i++) {
                CombinedResult r = results.get(competitions.get(i).getId());
                Integer v = r == null ? null : s.rank().apply(r);
                if (v != null) {
                    svg.append(String.format(Locale.ROOT,
                            "<circle cx='%.1f' cy='%.1f' r='4' class='fc-dot' style='fill:%s'/>", x(i), y(Math.min(v, yMax), yMax), s.color()));
                }
            }
        }
        // did not finish / start, disqualified: a hollow mark in the lane
        for (int i = 0; i < n; i++) {
            CombinedResult r = results.get(competitions.get(i).getId());
            if (r != null && r.getRank() == null && r.getStatus() != null && !r.getStatus().isBlank()) {
                svg.append(String.format(Locale.ROOT, "<circle cx='%.1f' cy='%d' r='4' class='fc-out'/>", x(i), laneY));
            }
        }
        // hover targets on top: the full column of each competition
        List<String> tips = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            Competition c = competitions.get(i);
            svg.append(String.format(Locale.ROOT,
                    "<rect class='fc-hit' data-i='%d' data-x='%.1f' data-id='%d' x='%.1f' y='%d' width='%d' height='%d'/>",
                    i, x(i), c.getId(), LEFT + i * (double) STEP, TOP, STEP, PLOT + LANE));
            tips.add(tooltip(c, results.get(c.getId())));
        }
        svg.append("</svg>");

        Div root = new Div();
        root.addClassName("form-chart");
        root.getElement().setProperty("innerHTML", STYLE + "<div class='fc-scroll'>" + svg + "</div><div class='fc-tip'></div>");
        root.getElement().executeJs(SCRIPT, toJsonArray(tips));
        return root;
    }

    private static double x(int i) {
        return LEFT + i * STEP + STEP / 2.0;
    }

    private static double y(double rank, int yMax) {
        return TOP + (rank - 1) / (yMax - 1.0) * PLOT;
    }

    private static String rect(double x, double y, double w, double h, String style) {
        return String.format(Locale.ROOT, "<rect x='%.1f' y='%.1f' width='%.1f' height='%.1f' style='%s'/>", x, y, w, h, style);
    }

    private static String text(double x, double y, String s, String anchor, String cls) {
        return String.format(Locale.ROOT, "<text x='%.1f' y='%.1f' text-anchor='%s' class='%s'>%s</text>", x, y, anchor, cls, esc(s));
    }

    private static String tooltip(Competition c, CombinedResult r) {
        StringBuilder t = new StringBuilder();
        t.append("<b>").append(esc(c.getDisplayLocation())).append("</b> · ").append(esc(c.getCompetitionDate()))
                .append("<br><span class='fc-muted'>").append(esc(c.getFormat() == null ? "" : c.getFormat())).append("</span>");
        if (r == null) {
            t.append("<br>did not start");
        } else if (r.getRank() == null) {
            t.append("<br>").append(esc(r.getStatus() == null ? "no rank" : r.getStatus()));
        } else {
            t.append("<br>Rank <b>").append(r.getRank()).append("</b>");
        }
        if (r != null) {
            if (r.getJumpRank() != null) t.append(" · Jump ").append(r.getJumpRank());
            if (r.getXcRank() != null) t.append(" · XC ").append(r.getXcRank());
        }
        return t.toString();
    }

    static String shortVenue(String venue) {
        if (venue == null) return "";
        return venue.length() <= 11 ? venue : venue.substring(0, 10) + "…";
    }

    private static String shortDate(String iso) {
        if (iso == null || iso.length() < 10) return "";
        return Integer.parseInt(iso.substring(8, 10)) + "." + Integer.parseInt(iso.substring(5, 7)) + ".";
    }

    static String esc(String s) {
        if (s == null) return "";
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;").replace("\"", "&quot;");
    }

    private static String toJsonArray(List<String> items) {
        StringBuilder json = new StringBuilder("[");
        for (int i = 0; i < items.size(); i++) {
            if (i > 0) json.append(',');
            json.append('"').append(items.get(i).replace("\\", "\\\\").replace("\"", "\\\"")).append('"');
        }
        return json.append(']').toString();
    }

    // Light values and the dark steps of the same three hues (Lumo dark theme)
    private static final String STYLE = """
            <style>
            .form-chart { position: relative; --fc-s1:#2a78d6; --fc-s2:#eb6834; --fc-s3:#1baf7a;
                          --fc-band: var(--lumo-contrast-10pct); --fc-surface: var(--lumo-base-color); }
            html[theme~="dark"] .form-chart { --fc-s1:#3987e5; --fc-s2:#d95926; --fc-s3:#199e70; }
            .form-chart .fc-scroll { overflow-x: auto; }
            .form-chart .fc-grid { stroke: var(--lumo-contrast-10pct); stroke-width: 1; }
            .form-chart .fc-axis { fill: var(--lumo-secondary-text-color); font-size: 11px; }
            .form-chart .fc-muted { fill: var(--lumo-tertiary-text-color); color: var(--lumo-secondary-text-color); font-size: 11px; }
            .form-chart .fc-label { fill: var(--lumo-body-text-color); font-size: 12px; }
            .form-chart .fc-line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
            .form-chart .fc-dot { stroke: var(--fc-surface); stroke-width: 2; }
            .form-chart .fc-out { fill: var(--fc-surface); stroke: var(--lumo-secondary-text-color); stroke-width: 2; }
            .form-chart .fc-cross { stroke: var(--lumo-contrast-30pct); stroke-width: 1; }
            .form-chart .fc-hit { fill: transparent; cursor: pointer; }
            .form-chart .fc-tip { position: absolute; display: none; pointer-events: none; z-index: 2;
                                  background: var(--lumo-base-color); color: var(--lumo-body-text-color);
                                  border: 1px solid var(--lumo-contrast-20pct); border-radius: var(--lumo-border-radius-m);
                                  box-shadow: var(--lumo-box-shadow-s); padding: 6px 10px;
                                  font-size: var(--lumo-font-size-s); line-height: 1.5; white-space: nowrap; }
            </style>
            """;

    private static final String SCRIPT = """
            const root = this, tips = JSON.parse($0);
            const svg = root.querySelector('svg'), tip = root.querySelector('.fc-tip'), cross = root.querySelector('.fc-cross');
            root.querySelectorAll('.fc-hit').forEach(hit => {
              hit.addEventListener('mouseenter', () => {
                cross.setAttribute('x1', hit.dataset.x); cross.setAttribute('x2', hit.dataset.x);
                cross.style.display = ''; tip.innerHTML = tips[+hit.dataset.i]; tip.style.display = 'block';
              });
              hit.addEventListener('mousemove', e => {
                const box = root.getBoundingClientRect();
                let left = e.clientX - box.left + 14;
                if (left + tip.offsetWidth > box.width) left = e.clientX - box.left - tip.offsetWidth - 14;
                tip.style.left = left + 'px'; tip.style.top = (e.clientY - box.top + 12) + 'px';
              });
              hit.addEventListener('click', () => window.location.assign('result/' + hit.dataset.id));
            });
            svg.addEventListener('mouseleave', () => { tip.style.display = 'none'; cross.style.display = 'none'; });
            """;
}
