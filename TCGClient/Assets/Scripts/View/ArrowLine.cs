using UnityEngine;
using UnityEngine.UI;

namespace Tcg.View
{
    /// <summary>A quadratic curve drawn as dots: a continuous navy edge under spaced coloured dots.</summary>
    public class ArrowLine : MaskableGraphic
    {
        Vector2 _a, _b, _c;
        Color _colour = Color.white;

        public override Texture mainTexture =>
            Ui.Theme != null && Ui.Theme.Dot != null ? Ui.Theme.Dot.texture : s_WhiteTexture;

        public void Set(Vector2 from, Vector2 control, Vector2 to, Color colour)
        {
            _a = from;
            _b = control;
            _c = to;
            _colour = colour;
            SetVerticesDirty();
        }

        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            float length = Vector2.Distance(_a, _b) + Vector2.Distance(_b, _c);
            if (length < 1f) return;
            Dots(vh, length, 4f, 16f, Palette.Shadow);
            Dots(vh, length, 17f, 9f, _colour);
        }

        void Dots(VertexHelper vh, float length, float spacing, float size, Color colour)
        {
            int n = Mathf.Max(1, Mathf.FloorToInt(length / spacing));
            for (int i = 0; i <= n; i++)
            {
                float t = i / (float)n;
                float u = 1f - t;
                Vector2 p = u * u * _a + 2f * u * t * _b + t * t * _c;
                Quad(vh, p, size / 2f, colour);
            }
        }

        static void Quad(VertexHelper vh, Vector2 p, float r, Color colour)
        {
            int start = vh.currentVertCount;
            vh.AddVert(p + new Vector2(-r, -r), colour, new Vector2(0, 0));
            vh.AddVert(p + new Vector2(-r, r), colour, new Vector2(0, 1));
            vh.AddVert(p + new Vector2(r, r), colour, new Vector2(1, 1));
            vh.AddVert(p + new Vector2(r, -r), colour, new Vector2(1, 0));
            vh.AddTriangle(start, start + 1, start + 2);
            vh.AddTriangle(start + 2, start + 3, start);
        }
    }
}
