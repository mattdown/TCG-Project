using UnityEngine;

namespace Tcg.View
{
    /// <summary>Colour tokens from docs/client-design.md (the Lantern look: smoked glass and spore-light).</summary>
    public static class Palette
    {
        public static readonly Color Shadow = Hex("#06100D");     // text outlines, drop shadows
        public static readonly Color Night = Hex("#0B1612");      // behind everything, full-screen panels
        public static readonly Color Glass = Hex("#091310");      // panel fill, drawn at ~78% alpha
        public static readonly Color GlassRim = Hex("#A0EBD7").WithAlpha(0.3f);
        public static readonly Color Lantern = Hex("#7EF0D8");    // the glowing caps: primary buttons, glows
        public static readonly Color LanternText = Hex("#E6FBF4");
        public static readonly Color Firefly = Hex("#F4C76B");    // warm accent: callouts, choices, previews
        public static readonly Color CardShadow = Hex("#050A08");
        public static readonly Color TextBox = Hex("#E9EEF8");
        public static readonly Color BodyText = Hex("#24304F");
        public static readonly Color ParchmentText = Hex("#4A3726");  // text on the card frame's parchment
        public static readonly Color ParchmentBold = Hex("#1C1209");  // bold lead-ins and keywords there
        public static readonly Color SubtleText = Hex("#A9C9BC");
        public static readonly Color TraitText = Hex("#D8EAE2");
        public static readonly Color Energy = Hex("#E24BD6");
        public static readonly Color Health = Hex("#E8364F");
        public static readonly Color StatUp = Hex("#7CFF7C");
        public static readonly Color StatDown = Hex("#FF8A96");
        public static readonly Color GlowPlayable = Lantern;
        public static readonly Color GlowSelected = Hex("#FFE08A");
        public static readonly Color GlowUnusable = Hex("#F0A84A");  // affordable, but can't be played now
        public static readonly Color GlowTarget = Hex("#FF6A5C");
        public static readonly Color OpponentAccent = Hex("#FF8A7A");
        public static readonly Color HumanAccent = Hex("#5FD4BE");
        public static readonly Color Muted = Hex("#8FA79D");         // buttons with nothing to do

        /// <summary>Aspect colours by aspect_N (Ember, Bog, Moss, Meadow, Glow, Frost: see docs/theme.md).</summary>
        static readonly Color[] Aspects =
        {
            Hex("#F0533A"), Hex("#2F86E8"), Hex("#43B04F"), Hex("#F5B52E"), Hex("#9152E0"), Hex("#22BCC9"),
        };

        /// <summary>1-based aspect number from an id like "aspect_3"; 0 if unknown.</summary>
        public static int AspectNumber(string aspectId)
        {
            if (aspectId == null) return 0;
            int underscore = aspectId.LastIndexOf('_');
            return underscore >= 0 && int.TryParse(aspectId.Substring(underscore + 1), out int n) &&
                   n >= 1 && n <= Aspects.Length ? n : 0;
        }

        /// <summary>Neutral cards (no aspect): grey (docs/theme.md).</summary>
        public static readonly Color Neutral = Hex("#8A93AD");

        public static Color Aspect(int number) => number >= 1 ? Aspects[number - 1] : Neutral;

        public static Color Hex(string hex) => ColorUtility.TryParseHtmlString(hex, out var c) ? c : Color.magenta;

        public static Color WithAlpha(this Color c, float a) => new Color(c.r, c.g, c.b, a);
    }
}
