using UnityEngine;
using UnityEngine.UI;

namespace Tcg.View
{
    /// <summary>
    /// The drag arrow from a unit (docs/client-design.md, "Interaction"): a curved dotted line with a
    /// navy edge, an arrowhead, and a ring round the target. Points are in the parent's local space.
    /// </summary>
    public class ArrowView : MonoBehaviour
    {
        public ArrowLine Line;
        public Image Head;
        public Image Ring;

        public static ArrowView Create(RectTransform parent)
        {
            var root = Ui.Stretch("Arrow", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<ArrowView>();
            var line = Ui.Stretch("Line", root, 0, 0, 0, 0).gameObject;
            line.AddComponent<CanvasRenderer>();
            view.Line = line.AddComponent<ArrowLine>();
            view.Line.raycastTarget = false;
            view.Ring = Ui.Img(Ui.Node("Ring", root), Ui.Theme.TargetRing, Color.white);
            view.Ring.rectTransform.sizeDelta = new Vector2(64, 64);
            view.Head = Ui.Img(Ui.Node("Head", root), Ui.Theme.ArrowHead, Color.white);
            view.Head.rectTransform.sizeDelta = new Vector2(34, 34);
            view.Head.rectTransform.pivot = new Vector2(34f / 36f, 0.5f);
            view.Hide();
            return view;
        }

        public void Show(Vector2 from, Vector2 to, Color colour, bool ring)
        {
            gameObject.SetActive(true);
            // Bow the curve upwards, like the mockup's arcs.
            var mid = (from + to) / 2f;
            var control = mid + new Vector2(0f, Mathf.Min(160f, Vector2.Distance(from, to) * 0.35f));
            Vector2 tangent = (to - control).normalized;
            Line.Set(from, control, to - tangent * 18f, colour);
            Head.color = colour;
            Head.rectTransform.anchoredPosition = to;
            Head.rectTransform.localRotation = Quaternion.Euler(0, 0, Mathf.Atan2(tangent.y, tangent.x) * Mathf.Rad2Deg);
            Ring.gameObject.SetActive(ring);
            Ring.color = colour;
            Ring.rectTransform.anchoredPosition = to;
        }

        public void Hide() => gameObject.SetActive(false);
    }
}
