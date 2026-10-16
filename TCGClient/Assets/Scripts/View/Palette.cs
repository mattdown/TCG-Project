using UnityEngine;

namespace Tcg.View
{
    /// <summary>Colour tokens from docs/client-design.md.</summary>
    public static class Palette
    {
        public static readonly Color Outline = Hex("#0E1733");
        public static readonly Color CardNavy = Hex("#16203D");
        public static readonly Color UiNavy = Hex("#1E2C55");
        public static readonly Color CardShadow = Hex("#0A1022");
        public static readonly Color TextBox = Hex("#E9EEF8");
        public static readonly Color BodyText = Hex("#24304F");
        public static readonly Color SubtleText = Hex("#B8C6E8");
        public static readonly Color TraitText = Hex("#D6E0F5");
        public static readonly Color Energy = Hex("#E24BD6");
        public static readonly Color EnergySpent = Hex("#3A2558");
        public static readonly Color Power = Hex("#F08A24");
        public static readonly Color Health = Hex("#E8364F");
        public static readonly Color Gold = Hex("#FFC93C");
        public static readonly Color GoldLip = Hex("#D98A10");
        public static readonly Color StatUp = Hex("#7CFF7C");
        public static readonly Color StatDown = Hex("#FF8A96");
        public static readonly Color GlowPlayable = Hex("#5BEA5B");
        public static readonly Color GlowSelected = Hex("#FFE14D");
        public static readonly Color GlowTarget = Hex("#FF4D5E");
        public static readonly Color Exhausted = new Color(10 / 255f, 16 / 255f, 36 / 255f, 0.6f);
        public static readonly Color Zz = Hex("#BFD3FF");
        public static readonly Color OpponentAccent = Hex("#E0503C");
        public static readonly Color OpponentLip = Hex("#A8321F");
        public static readonly Color OpponentVp = Hex("#F0533A");
        public static readonly Color HumanAccent = Hex("#2F86E8");
        public static readonly Color HumanLip = Hex("#1A5DB0");
        public static readonly Color CardBack = Hex("#7A3FC4");
        public static readonly Color CardBackRing = Hex("#9152E0");

        /// <summary>Aspect colours by aspect_N (placeholder names Ember, Tide, Grove, Sun, Dusk, Frost).</summary>
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

        public static Color Aspect(int number) => number >= 1 ? Aspects[number - 1] : Hex("#7A88A8");

        public static Color Hex(string hex) => ColorUtility.TryParseHtmlString(hex, out var c) ? c : Color.magenta;

        public static Color WithAlpha(this Color c, float a) => new Color(c.r, c.g, c.b, a);
    }
}
