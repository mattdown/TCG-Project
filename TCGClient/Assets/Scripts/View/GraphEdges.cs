using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.View
{
    /// <summary>Every edge of the GNN overlay in one mesh: straight or bent lines, with an arrowhead if directed.</summary>
    public class GraphEdges : MaskableGraphic
    {
        public struct Edge
        {
            public Vector2 From, To;
            public Color Colour;
            public float Width;
            public float Bend;   // control point offset as a share of the length; 0 is straight
            public float Inset;  // stop this far short of To (the target node's radius)
            public bool Arrow;
        }

        readonly List<Edge> _edges = new List<Edge>();

        public void Set(List<Edge> edges)
        {
            _edges.Clear();
            _edges.AddRange(edges);
            SetVerticesDirty();
        }

        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            foreach (var e in _edges)
            {
                var d = e.To - e.From;
                float length = d.magnitude;
                if (length < 1f) continue;
                var normal = new Vector2(-d.y, d.x) / length;
                var control = (e.From + e.To) / 2f + normal * (e.Bend * length);
                var tangent = (e.To - (e.Bend == 0f ? e.From : control)).normalized;
                var end = e.To - tangent * e.Inset;
                int segments = e.Bend == 0f ? 1 : Mathf.Clamp(Mathf.RoundToInt(length / 14f), 4, 24);
                var previous = e.From;
                for (int i = 1; i <= segments; i++)
                {
                    float t = i / (float)segments, u = 1f - t;
                    var p = e.Bend == 0f ? end : u * u * e.From + 2f * u * t * control + t * t * end;
                    Segment(vh, previous, p, e.Width, e.Colour);
                    previous = p;
                }
                if (e.Arrow)
                {
                    float size = 3f + e.Width * 1.6f;
                    var side = new Vector2(-tangent.y, tangent.x) * (size * 0.6f);
                    var back = end - tangent * size;
                    Triangle(vh, end, back + side, back - side, e.Colour);
                }
            }
        }

        static void Segment(VertexHelper vh, Vector2 a, Vector2 b, float width, Color colour)
        {
            var d = (b - a).normalized;
            var n = new Vector2(-d.y, d.x) * (width / 2f);
            var along = d * (width / 4f);  // overlap the joints of bent lines
            int start = vh.currentVertCount;
            vh.AddVert(a - along - n, colour, Vector2.zero);
            vh.AddVert(a - along + n, colour, Vector2.zero);
            vh.AddVert(b + along + n, colour, Vector2.zero);
            vh.AddVert(b + along - n, colour, Vector2.zero);
            vh.AddTriangle(start, start + 1, start + 2);
            vh.AddTriangle(start + 2, start + 3, start);
        }

        static void Triangle(VertexHelper vh, Vector2 a, Vector2 b, Vector2 c, Color colour)
        {
            int start = vh.currentVertCount;
            vh.AddVert(a, colour, Vector2.zero);
            vh.AddVert(b, colour, Vector2.zero);
            vh.AddVert(c, colour, Vector2.zero);
            vh.AddTriangle(start, start + 1, start + 2);
        }
    }
}
