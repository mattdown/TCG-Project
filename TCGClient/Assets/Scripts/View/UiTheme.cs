using TMPro;
using UnityEngine;

namespace Tcg.View
{
    /// <summary>The shared sprites and fonts, so the editor builder and runtime overlays draw alike.</summary>
    [CreateAssetMenu(menuName = "TCG/UI Theme")]
    public class UiTheme : ScriptableObject
    {
        [Header("Sprites")]
        public Sprite Rounded;      // white rounded rect, 9-sliced, radius 16
        public Sprite Ring;         // white rounded outline, 9-sliced, radius 16, 3 px
        public Sprite Glow;
        public Sprite Dot;
        public Sprite TargetRing;
        public Sprite ArrowHead;
        public Sprite Stripes;
        public Sprite Crown;

        [Header("Fonts")]
        public TMP_FontAsset Lilita;
        public TMP_FontAsset Nunito;
        public TMP_FontAsset NunitoBlack;
        [Tooltip("Lilita One with a dark outline and drop shadow, for numbers, names and buttons.")]
        public Material LilitaOutline;
    }
}
