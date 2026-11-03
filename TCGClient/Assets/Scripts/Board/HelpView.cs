using System.Collections.Generic;
using System.Linq;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.Board
{
    /// <summary>
    /// The help screen (the mockup's "6 · Help: how to read a card"): a sample unit from the card
    /// set at 2× with a callout for each part, the keywords and the classes. Every rule and name on
    /// it comes from the server's card_set; the callouts aim at the card's own parts, so they
    /// follow layout changes to the card.
    /// </summary>
    public class HelpView : MonoBehaviour
    {
        const float CardScale = 2f;
        static readonly Color Callout = Palette.Firefly;
        static readonly Color PanelRing = Palette.Lantern.WithAlpha(0.25f);

        public bool IsOpen => gameObject.activeSelf;

        RectTransform _cardArea, _callouts, _keywords, _classes;
        CardView _card;
        TMP_Text _notes;
        readonly List<GameObject> _built = new List<GameObject>();

        public static HelpView Create(RectTransform parent, CardView prefab)
        {
            var root = Ui.Stretch("Help", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<HelpView>();
            Ui.Scrim(root, "Scrim", 0.82f).onClick.AddListener(view.Hide);

            // Laid out on the 1280x720 design, centred on wider screens.
            var page = Ui.Node("Page", root);
            Ui.Anchor(page, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(1280, 720));
            var panel = Ui.Box("Panel", page, 24, 24, 1232, 672);
            Ui.Panel(panel, 22, Palette.Lantern.WithAlpha(0.4f), 0.94f).raycastTarget = true;  // taps on the panel don't close it

            Ui.Display(Ui.Box("Title", page, 52, 46, 600, 36), UiText.HelpTitle, 30, TextAlignmentOptions.Left);
            var close = Ui.Box("Close", page, 1184, 44, 44, 44);
            Ui.Button(close, "✕", Palette.OpponentAccent, 20, out var closeLabel).onClick.AddListener(view.Hide);
            closeLabel.characterSpacing = 0f;

            view._cardArea = Ui.Box("CardArea", page, 52, 102, 600, 566);
            view._callouts = Ui.Box("Callouts", page, 52, 102, 600, 566);
            view._card = Instantiate(prefab, view._cardArea);
            view._card.Input.Handler = null;
            view._card.Group.blocksRaycasts = false;
            var rt = view._card.Rect;
            rt.anchorMin = rt.anchorMax = new Vector2(0, 1);
            rt.anchoredPosition = new Vector2(300, -230);  // a 300x420 card with its top-left at (150, 20)
            rt.localScale = Vector3.one * CardScale;

            // Below the card and the job's label.
            view._notes = Ui.Text(Ui.Box("Notes", view._cardArea, 100, 506, 400, 60), "", Ui.Theme.Body, 13,
                Palette.SubtleText, TextAlignmentOptions.Top);
            view._notes.textWrappingMode = TextWrappingModes.Normal;
            view._notes.lineSpacing = 10f;

            Divider(page, 676);
            view._keywords = Column(page, "Keywords", 701, UiText.HelpKeywords);
            Divider(page, 961);
            view._classes = Column(page, "Classes", 986, UiText.HelpClasses);

            root.gameObject.SetActive(false);
            return view;
        }

        /// <summary>Opens the screen with a sample unit from <paramref name="defs"/> (none: no card).</summary>
        public void Show(IReadOnlyDictionary<string, CardDef> defs)
        {
            foreach (var go in _built) Destroy(go);
            _built.Clear();
            gameObject.SetActive(true);
            transform.SetAsLastSibling();

            var sample = PickSample(defs);
            _card.gameObject.SetActive(sample != null);
            if (sample != null)
            {
                _card.Bind(sample, null);
                _card.SetMark(CardMark.None);
                Callouts();
            }
            _notes.text = Notes();

            foreach (var kv in CardText.Keywords)
            {
                string name = kv.Value.numbered ? $"{kv.Value.name} +N" : kv.Value.name;
                KeywordBox(name, kv.Value.rule);
            }
            foreach (var kv in CardText.Aspects)
                ClassRow(kv.Value.name, kv.Value.description, kv.Key == "neutral" ? Palette.Neutral : Palette.Aspect(Palette.AspectNumber(kv.Key)));
            LayoutRebuilder.ForceRebuildLayoutImmediate(_keywords);
            LayoutRebuilder.ForceRebuildLayoutImmediate(_classes);
        }

        public void Hide() => gameObject.SetActive(false);

        /// <summary>A unit that shows every part: a keyword, ability text and a subtitle, if the set has one.</summary>
        static CardDef PickSample(IReadOnlyDictionary<string, CardDef> defs)
        {
            if (defs == null) return null;
            CardDef best = null;
            int bestScore = -1;
            foreach (var def in defs.Values)
            {
                if (def.IsAction) continue;
                int score = (def.keywords != null && def.keywords.Count > 0 ? 1 : 0)
                          + (def.ability_text != null && def.ability_text.Count > 0 ? 1 : 0)
                          + (!string.IsNullOrEmpty(def.subtitle) ? 1 : 0);
                if (score > bestScore || (score == bestScore && string.CompareOrdinal(def.id, best.id) < 0))
                {
                    best = def;
                    bestScore = score;
                }
            }
            return best;
        }

        static string Notes()
        {
            string charge = CardText.KeywordLabel("charge", 1);
            return string.Format(UiText.HelpNoteStats, ColorUtility.ToHtmlStringRGB(Palette.StatUp),
                       ColorUtility.ToHtmlStringRGB(Palette.StatDown)) + "\n"
                   + string.Format(UiText.HelpNoteFresh, charge) + "\n"
                   + UiText.HelpNoteFrozen;
        }

        // --- the callouts: each label's line ends on the card part it describes

        enum Side { Left, Right, Below }

        const float LabelWidth = 126f, LabelHeight = 60f, LabelGap = 6f;

        void Callouts()
        {
            // Points in the callout layer: x right, y down from its top-left (as in the mockup).
            Vector2 Local(Transform part, Vector3 point)
            {
                var local = (Vector2)_callouts.InverseTransformPoint(part.TransformPoint(point));
                return new Vector2(local.x, -local.y);
            }

            // A point on the text as drawn (u, v across its bounds, v down), not on its box, so a
            // pointer lands on the number or word whatever the alignment and auto-size did.
            Vector2 OnText(TMP_Text text, float u, float v)
            {
                text.ForceMeshUpdate();
                var b = text.textBounds;
                return Local(text.transform, new Vector3(b.min.x + b.size.x * u, b.max.y - b.size.y * v));
            }

            // The end of the rules text's first line: the keywords.
            Vector2 FirstLineEnd(TMP_Text text)
            {
                text.ForceMeshUpdate();
                if (text.textInfo.lineCount == 0) return OnText(text, 1f, 0.5f);
                var line = text.textInfo.lineInfo[0];
                return Local(text.transform, new Vector3(line.lineExtents.max.x + 3f, (line.ascender + line.descender) / 2f));
            }

            Stack(Side.Left,
                (UiText.HelpCost, UiText.HelpCostText, OnText(_card.CostText, 0.5f, 0.5f)),
                (UiText.HelpName, UiText.HelpNameText, OnText(_card.NameText, 0f, 0.5f) - new Vector2(5f, 0f)),
                (UiText.HelpAttack, UiText.HelpAttackText, OnText(_card.PowerText, 0.5f, 0.5f)));
            Stack(Side.Right,
                (UiText.HelpRules, UiText.HelpRulesText, FirstLineEnd(_card.BodyText)),
                (UiText.HelpHealth, UiText.HelpHealthText, OnText(_card.HealthText, 0.5f, 0.5f)));
            // The job banner sits between the attack disc and the shield, so its label goes below the card.
            var job = OnText(_card.TraitText, 0.5f, 1f) + new Vector2(0f, 3f);
            Label(UiText.HelpJob, UiText.HelpJobText, job, Side.Below, job.y + 12f);
        }

        /// <summary>One side's labels, each level with its target where it can be, pushed down so none overlap.</summary>
        void Stack(Side side, params (string title, string text, Vector2 target)[] labels)
        {
            float next = float.MinValue;
            foreach (var l in labels.OrderBy(l => l.target.y))
            {
                float top = Mathf.Max(l.target.y - 18f, next);
                Label(l.title, l.text, l.target, side, top);
                next = top + LabelHeight + LabelGap;
            }
        }

        void Label(string title, string text, Vector2 target, Side side, float top)
        {
            float width = side == Side.Below ? 2 * LabelWidth : LabelWidth;
            float x = side switch { Side.Left => 0f, Side.Right => 474f, _ => target.x - width / 2f };
            var box = Ui.Box(title, _callouts, x, top, width, LabelHeight);
            var align = side switch
            {
                Side.Left => TextAlignmentOptions.TopRight,
                Side.Right => TextAlignmentOptions.TopLeft,
                _ => TextAlignmentOptions.Top,
            };
            Ui.Text(Ui.Box("Title", box, 0, 0, width, 22), title, Ui.Theme.Display, 17, Callout, align);
            var b = Ui.Text(Ui.Box("Text", box, 0, 20, width, 40), text, Ui.Theme.Body, 13, Palette.TraitText, align);
            b.textWrappingMode = TextWrappingModes.Normal;
            _built.Add(box.gameObject);

            var from = side switch
            {
                Side.Left => new Vector2(x + width + 2f, top + 18f),
                Side.Right => new Vector2(x - 4f, top + 18f),
                _ => new Vector2(target.x, top + 2f),
            };
            Line(from, target);
        }

        void Line(Vector2 from, Vector2 to)
        {
            var d = to - from;
            var line = Ui.Node("Line", _callouts);
            line.anchorMin = line.anchorMax = new Vector2(0, 1);
            line.pivot = new Vector2(0, 0.5f);
            line.anchoredPosition = new Vector2(from.x, -from.y);
            line.sizeDelta = new Vector2(d.magnitude, 2f);
            line.localRotation = Quaternion.Euler(0, 0, -Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg);
            Ui.Img(line, null, Callout);
            var dot = Ui.Node("Dot", _callouts);
            dot.anchorMin = dot.anchorMax = new Vector2(0, 1);
            dot.anchoredPosition = new Vector2(to.x, -to.y);
            dot.sizeDelta = new Vector2(8, 8);
            Ui.Img(dot, Ui.Theme.Dot, Callout);
            _built.Add(line.gameObject);
            _built.Add(dot.gameObject);
        }

        // --- the keyword and class columns

        static void Divider(RectTransform page, float x) =>
            Ui.Img(Ui.Box("Divider", page, x, 102, 1, 566), null, PanelRing);

        static RectTransform Column(RectTransform page, string name, float x, string title)
        {
            var col = Ui.Box(name, page, x, 102, 236, 566);
            var layout = col.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.spacing = 10;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            var heading = Ui.Display(Ui.Node("Title", col), title, 20, TextAlignmentOptions.Left);
            heading.gameObject.AddComponent<LayoutElement>().minHeight = 26;
            return col;
        }

        void KeywordBox(string name, string rule)
        {
            var box = Ui.Node("Keyword", _keywords);
            Ui.Panel(box, 12, Palette.Lantern.WithAlpha(0.4f));
            var layout = box.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(14, 14, 10, 11);
            layout.spacing = 3;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            Ui.Text(Ui.Node("Name", box), name, Ui.Theme.Display, 17, Palette.Lantern, TextAlignmentOptions.Left);
            var text = Ui.Text(Ui.Node("Rule", box), rule, Ui.Theme.Body, 13, Palette.TraitText, TextAlignmentOptions.TopLeft);
            text.textWrappingMode = TextWrappingModes.Normal;
            _built.Add(box.gameObject);
        }

        void ClassRow(string name, string feel, Color colour)
        {
            var row = Ui.Node("Class", _classes);
            Ui.Panel(row, 12);
            var layout = row.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.padding = new RectOffset(9, 10, 8, 8);
            layout.spacing = 10;
            layout.childAlignment = TextAnchor.MiddleLeft;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;

            var swatch = Ui.Node("Swatch", row);
            var size = swatch.gameObject.AddComponent<LayoutElement>();
            size.minWidth = size.preferredWidth = 30;
            size.minHeight = size.preferredHeight = 30;
            Ui.Rounded(swatch, colour.WithAlpha(0.3f), Ui.Round);
            Ui.Rim(Ui.Stretch("Rim", swatch, 0, 0, 0, 0), colour, Ui.Round);
            Ui.Rounded(Ui.Stretch("Light", swatch, 9, 9, 9, 9), colour, Ui.Round);

            var words = Ui.Node("Words", row);
            words.gameObject.AddComponent<LayoutElement>().flexibleWidth = 1;
            var stack = words.gameObject.AddComponent<VerticalLayoutGroup>();
            stack.spacing = 1;
            stack.childControlWidth = stack.childControlHeight = true;
            stack.childForceExpandWidth = true;
            stack.childForceExpandHeight = false;
            Ui.Text(Ui.Node("Name", words), name, Ui.Theme.Display, 16, Palette.LanternText, TextAlignmentOptions.Left);
            var text = Ui.Text(Ui.Node("Feel", words), feel, Ui.Theme.Body, 12, Palette.SubtleText, TextAlignmentOptions.TopLeft);
            text.textWrappingMode = TextWrappingModes.Normal;
            _built.Add(row.gameObject);
        }
    }
}
