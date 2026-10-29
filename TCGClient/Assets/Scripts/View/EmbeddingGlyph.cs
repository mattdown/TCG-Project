using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.View
{
    /// <summary>
    /// A node's vector as a square grid of cells: orange for positive values, blue for negative,
    /// fading to navy at zero. Values are read against a shared scale so nodes compare at a glance.
    /// </summary>
    public class EmbeddingGlyph : MaskableGraphic
    {
        public static readonly Color Positive = Palette.Hex("#FB923C");
        public static readonly Color Negative = Palette.Hex("#38BDF8");
        static readonly Color Zero = Palette.Outline;

        IList<float> _values;
        float _scale = 1f;

        public void Set(IList<float> values, float scale)
        {
            _values = values;
            _scale = Mathf.Max(scale, 1e-4f);
            SetVerticesDirty();
        }

        public static Color ColourOf(float value, float scale) =>
            Color.Lerp(Zero, value >= 0f ? Positive : Negative, Mathf.Clamp01(Mathf.Abs(value) / scale));

        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            if (_values == null || _values.Count == 0) return;
            var r = rectTransform.rect;
            int side = Mathf.CeilToInt(Mathf.Sqrt(_values.Count));
            float cell = Mathf.Min(r.width, r.height) / side;
            float gap = cell > 5f ? 1f : 0f;
            var origin = new Vector2(r.center.x - cell * side / 2f, r.center.y + cell * side / 2f);
            for (int i = 0; i < _values.Count; i++)
            {
                var min = origin + new Vector2(i % side * cell, -(i / side + 1) * cell);
                var colour = ColourOf(_values[i], _scale);
                int start = vh.currentVertCount;
                vh.AddVert(new Vector2(min.x, min.y), colour, Vector2.zero);
                vh.AddVert(new Vector2(min.x, min.y + cell - gap), colour, Vector2.zero);
                vh.AddVert(new Vector2(min.x + cell - gap, min.y + cell - gap), colour, Vector2.zero);
                vh.AddVert(new Vector2(min.x + cell - gap, min.y), colour, Vector2.zero);
                vh.AddTriangle(start, start + 1, start + 2);
                vh.AddTriangle(start + 2, start + 3, start);
            }
        }
    }
}
