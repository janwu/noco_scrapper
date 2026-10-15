package com.fis.noco.service;

import java.text.Normalizer;
import java.util.Map;

/**
 * Turns a name as a person types it ('Bjørnstad', 'Otepää', 'Štrbské') into the
 * spelling FIS uses and the database stores ('Bjoernstad', 'Otepaeae',
 * 'Strbske'), so that a search finds a name in either spelling.
 */
public final class NameFolding {

    private NameFolding() {
    }

    private static final Map<Character, String> LETTERS = Map.ofEntries(
            Map.entry('ä', "ae"), Map.entry('ö', "oe"), Map.entry('ü', "ue"), Map.entry('ß', "ss"),
            Map.entry('ø', "oe"), Map.entry('æ', "ae"), Map.entry('å', "aa"),
            Map.entry('Ä', "AE"), Map.entry('Ö', "OE"), Map.entry('Ü', "UE"),
            Map.entry('Ø', "OE"), Map.entry('Æ', "AE"), Map.entry('Å', "AA"),
            Map.entry('ł', "l"), Map.entry('Ł', "L"), Map.entry('đ', "d"), Map.entry('Đ', "D"));

    public static String toFis(String text) {
        StringBuilder out = new StringBuilder();
        for (char c : text.toCharArray()) {
            String replacement = LETTERS.get(c);
            out.append(replacement != null ? replacement : String.valueOf(c));
        }
        // other accents are dropped: é → e, š → s
        return Normalizer.normalize(out, Normalizer.Form.NFD).replaceAll("\\p{M}", "");
    }
}
