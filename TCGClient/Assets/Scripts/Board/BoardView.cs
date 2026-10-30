using System.Collections;
using System.Collections.Generic;
using DG.Tweening;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UI;

namespace Tcg.Board
{
    /// <summary>
    /// The landscape board (docs/client-design.md, "Layout"), designed at 1280x720. Renders a
    /// server state as it is: card GameObjects are keyed by uid so they survive zone changes, and
    /// what an action did (damage, defeats, hero damage, cards moving) is animated from the
    /// action record's result, as the server reports it.
    /// </summary>
    public class BoardView : MonoBehaviour
    {
        const float FieldScale = 0.86f;
        const float RowGap = 14f;
        const float MaxRowWidth = 900f;  // keeps a full row of 7 clear of the hero panels in the left corners
        const float HandStep = 118f;
        const float HandMaxWidth = 700f;
        const float BackVisible = 62f;     // how far the opponent's hand hangs into the board
        const float BackMaxWidth = 520f;   // narrower than yours, clear of their mana in the top right
        const float Move = 0.3f;
        const float BashGap = 26f;      // between attacker and target as it lines up
        const float BashOverlap = 22f;  // how far the attacker's edge sinks into the target on impact
        const float SpotlightScale = 1.7f;

        public UiTheme Theme;
        [Tooltip("The painted mana crystal, full and spent.")]
        public Sprite ManaFull, ManaEmpty;

        [Header("Cards")]
        public CardView CardPrefab;
        public RectTransform OpponentUnits, HumanUnits, Hand, OpponentBacks;
        public GameObject CardBackTemplate;

        [Header("Opponent bar")]
        [Tooltip("The enemy hero's panel: the attack_hero target.")]
        public RectTransform OpponentHero;
        [Tooltip("The name on the hero panel's banner.")]
        public TMP_Text OpponentNameText;
        [Tooltip("Deck and hand counts, beside the panel.")]
        public TMP_Text OpponentInfoText;
        public RectTransform OpponentHealthFill;
        public TMP_Text OpponentHealthText;
        public RectTransform OpponentCrystals;
        public TMP_Text OpponentManaText;

        [Header("Your side")]
        public RectTransform HumanHero;
        public TMP_Text HumanNameText;
        public TMP_Text HumanInfoText;
        public RectTransform HumanHealthFill;
        public TMP_Text HumanHealthText;
        public RectTransform HumanCrystals;
        public TMP_Text HumanManaText;
        public TMP_Text TurnText;
        public Button EndTurnButton;
        public TMP_Text EndTurnLabel;
        [Tooltip("Pulses behind END TURN when there's nothing else left to do.")]
        public Image EndTurnGlow;
        [Tooltip("Opens the help screen: how to read a card, the keywords and the classes.")]
        public Button HelpButton;
        [Tooltip("The second player's one-off +1 mana, shown while its action is legal.")]
        public Button SpareSporeButton;
        public TMP_Text SpareSporeLabel;

        [Header("Messages")]
        public TMP_Text MessageText;

        /// <summary>Gets taps and drags from every card on the board.</summary>
        public ICardInputHandler InputHandler { get; set; }
        public GameState State { get; private set; }
        public IReadOnlyDictionary<string, CardDef> Defs { get; private set; }
        public string OpponentName { get; private set; } = "";
        public RectTransform Root => (RectTransform)transform;
        public int HeroHealth => State != null && State.hero_health > 0 ? State.hero_health : 30;

        /// <summary>Above the cards: dragged cards, arrows and effects.</summary>
        public RectTransform TopLayer { get; private set; }

        readonly Dictionary<int, CardView> _cards = new Dictionary<int, CardView>();
        readonly Dictionary<int, string> _zoneOf = new Dictionary<int, string>();
        readonly Dictionary<int, Vector3> _spawnAt = new Dictionary<int, Vector3>();
        readonly List<GameObject> _backs = new List<GameObject>();
        float _opponentHealthWidth, _humanHealthWidth;
        RectTransform _ghost;
        Image _heroRing;
        CanvasGroup _handGroup;
        int _ghostSlots;

        void Awake()
        {
            Ui.Theme = Theme;
            _opponentHealthWidth = OpponentHealthFill.sizeDelta.x;
            _humanHealthWidth = HumanHealthFill.sizeDelta.x;
            _heroRing = OpponentHero.Find("TargetRing").GetComponent<Image>();
            CardBackTemplate.SetActive(false);
            _handGroup = Hand.gameObject.AddComponent<CanvasGroup>();

            TopLayer = Ui.Stretch("Top", Root, 0, 0, 0, 0);
            TopLayer.SetSiblingIndex(MessageText.transform.parent.GetSiblingIndex());

            _ghost = Ui.Node("Ghost", HumanUnits);
            _ghost.sizeDelta = new Vector2(CardView.Width * FieldScale, CardView.Height * FieldScale);
            Ui.Rounded(_ghost, Color.white.WithAlpha(0.28f), 12);
            _ghost.gameObject.SetActive(false);


            ShowMessage(UiText.Connecting);
        }

        // --- rendering

        /// <summary>
        /// Shows <paramref name="s"/>. With <paramref name="animate"/>, cards move to their new places
        /// and the result of <paramref name="action"/> (the last action) is played out first.
        /// </summary>
        public void Render(GameState s, IReadOnlyDictionary<string, CardDef> defs, string opponentName, bool animate,
            GameAction action = null)
        {
            var previous = State;
            Defs = defs;
            if (animate && previous != null && action?.result != null) PlayResult(action, previous.human_seat);
            State = s;
            Defs = defs;
            OpponentName = opponentName;
            animate &= previous != null;
            var human = s.Human;
            var opponent = s.Opponent;
            var playable = new HashSet<int>();
            foreach (var a in s.legal_actions)
                if (a.type == ActionTypes.Play && a.card.HasValue) playable.Add(a.card.Value);

            var seen = new HashSet<int>();
            LayoutRow(OpponentUnits, opponent.play, "opponent_play", seen, animate, 0);
            LayoutRow(HumanUnits, human.play, "human_play", seen, animate, _ghostSlots);
            LayoutHand(human.hand ?? new List<CardInstance>(), playable, seen, animate);
            RemoveCardsNotIn(seen, animate);
            LayoutBacks(opponent.hand_count);
            _handGroup.alpha = s.InMulligan ? 0f : 1f;
            _handGroup.blocksRaycasts = !s.InMulligan;

            OpponentNameText.text = opponentName;
            OpponentInfoText.text = $"{UiText.Deck} {opponent.deck_count}\n{UiText.Hand} {opponent.hand_count}";
            SetHealth(OpponentHealthFill, _opponentHealthWidth, OpponentHealthText, opponent.health, animate);
            SetCrystals(OpponentCrystals, OpponentManaText, opponent);

            HumanNameText.text = UiText.You;
            HumanInfoText.text = $"{UiText.Deck} {human.deck_count}";
            SetHealth(HumanHealthFill, _humanHealthWidth, HumanHealthText, human.health, animate);
            SetCrystals(HumanCrystals, HumanManaText, human);
            TurnText.text = $"{UiText.Turn} {s.turn}";

            var spore = Commands.Find(s, a => a.type == ActionTypes.SpareSpore);
            SpareSporeButton.gameObject.SetActive(spore != null);
            if (spore != null) SpareSporeLabel.text = spore.text.ToUpperInvariant();
            SetHeroTarget(false, false);
        }

        /// <summary>Re-lays out the current state, e.g. to snap a dropped card back.</summary>
        public void Relayout()
        {
            if (State != null) Render(State, Defs, OpponentName, true);
        }

        public CardView CardByUid(int uid) => _cards.TryGetValue(uid, out var v) ? v : null;

        public bool IsInHumanHand(int uid) => Zone(uid) == "hand";
        public bool IsHumanUnit(int uid) => Zone(uid) == "human_play";
        public bool IsOpponentUnit(int uid) => Zone(uid) == "opponent_play";
        string Zone(int uid) => _zoneOf.TryGetValue(uid, out var z) ? z : null;

        public IEnumerable<CardView> OpponentUnitViews()
        {
            if (State == null) yield break;
            foreach (var c in State.Opponent.play)
                if (_cards.TryGetValue(c.uid, out var v)) yield return v;
        }

        /// <summary>A point in TopLayer space for a world position.</summary>
        public Vector2 ToTop(Vector3 world) => TopLayer.InverseTransformPoint(world);

        /// <summary>END TURN keeps its label; it only greys out while it isn't yours to press.</summary>
        public void SetEndTurnButton(bool interactable)
        {
            EndTurnLabel.text = UiText.EndTurn;
            EndTurnButton.interactable = interactable;
        }

        /// <summary>Pulses a glow behind END TURN: nothing else is left to do this turn.</summary>
        public void SetEndTurnGlow(bool on)
        {
            if (on == EndTurnGlow.gameObject.activeSelf) return;
            EndTurnGlow.DOKill();
            EndTurnGlow.gameObject.SetActive(on);
            if (!on) return;
            EndTurnGlow.color = Palette.Gold.WithAlpha(0.35f);
            EndTurnGlow.DOFade(0.95f, 0.7f).SetEase(Ease.InOutSine).SetLoops(-1, LoopType.Yoyo);
        }

        /// <summary>A one-line notice (server errors, connection problems); null or empty hides it.</summary>
        public void ShowMessage(string text)
        {
            var box = MessageText.transform.parent;
            MessageText.text = text ?? "";
            box.gameObject.SetActive(!string.IsNullOrEmpty(text));
            if (!string.IsNullOrEmpty(text)) box.SetAsLastSibling();
        }

        // --- drag previews

        /// <summary>A light slot at the end of your row where a played card will land.</summary>
        public void ShowGhostSlot(bool show)
        {
            int slots = show ? 1 : 0;
            if (slots == _ghostSlots || State == null) return;
            _ghostSlots = slots;
            _ghost.gameObject.SetActive(show);
            LayoutRow(HumanUnits, State.Human.play, "human_play", new HashSet<int>(), true, _ghostSlots);
        }

        /// <summary>Outlines the full crystals a play would spend; 0 clears it.</summary>
        public void PreviewManaSpend(int spend)
        {
            var p = State.Human;
            for (int i = 0; i < HumanCrystals.childCount; i++)
            {
                var gem = HumanCrystals.GetChild(i);
                bool spent = i < spend && i < p.mana;
                gem.GetChild(0).gameObject.SetActive(spent);
                gem.GetChild(1).localScale = Vector3.one * (spent ? 1.1f : 1f);
            }
            HumanManaText.text = spend > 0 ? $"{p.mana} → {p.mana - spend}" : $"{p.mana}/{p.crystals}";
        }

        /// <summary>
        /// The enemy hero as an attack target: a faint ring while it's an option, a bright one under
        /// the finger with the health it would have left.
        /// </summary>
        public void SetHeroTarget(bool option, bool hovered, int damage = 0)
        {
            _heroRing.gameObject.SetActive(option);
            _heroRing.color = hovered ? Palette.GlowTarget : Palette.GlowTarget.WithAlpha(0.45f);
            int health = Mathf.Max(State?.Opponent.health ?? 0, 0);
            // The heart shows the health it would have left, in gold, while an attack on it is under the finger.
            bool preview = hovered && damage > 0;
            OpponentHealthText.text = (preview ? Mathf.Max(health - damage, 0) : health).ToString();
            OpponentHealthText.color = preview ? Palette.Gold : Color.white;
        }

        // --- the opponent's actions

        /// <summary>What happens before the state changes: the arrow of an attack, on a unit or your hero.</summary>
        public IEnumerator ShowAction(GameAction action, ArrowView arrow)
        {
            var actor = action.card.HasValue ? CardByUid(action.card.Value) : null;
            if (actor == null || (action.type != ActionTypes.Attack && action.type != ActionTypes.AttackHero)) yield break;
            var target = action.type == ActionTypes.Attack && action.target.HasValue ? CardByUid(action.target.Value) : null;
            if (action.type == ActionTypes.Attack && target == null) yield break;
            // The AI attacks your units or your hero (the panel bottom left).
            Vector3 at = target != null ? target.Rect.position : HumanHealthText.transform.position;
            actor.SetMark(CardMark.Selected);
            target?.SetTargetRing(TargetRing.Hovered);
            arrow.Show(ToTop(actor.Rect.position), ToTop(at), Palette.GlowTarget, true);
            yield return new WaitForSeconds(0.55f);
            arrow.Hide();
            actor.SetMark(CardMark.None);
            target?.SetTargetRing(TargetRing.None);
        }

        /// <summary>
        /// An attack, either side's, before the state changes: the attacker lines up with its target
        /// (below it from your row, above it from theirs), draws back, then bashes into it. The
        /// result and the new layout follow, so a survivor slides home and a defeated one dies where it hit.
        /// </summary>
        public IEnumerator Bash(GameAction action)
        {
            if (action == null || !action.card.HasValue ||
                (action.type != ActionTypes.Attack && action.type != ActionTypes.AttackHero)) yield break;
            var actor = CardByUid(action.card.Value);
            if (actor == null) yield break;
            bool fromBelow = IsHumanUnit(actor.Uid);
            var target = action.type == ActionTypes.AttackHero ? (fromBelow ? OpponentHero : HumanHero)
                : action.target.HasValue ? CardByUid(action.target.Value)?.Rect : null;
            if (target == null) yield break;

            var rt = actor.Rect;
            rt.DOKill();
            actor.SetMark(CardMark.None);
            rt.SetParent(TopLayer, true);  // over both rows; the next layout puts it back
            float unit = Root.lossyScale.y;
            float reach = (rt.rect.height * rt.lossyScale.y + target.rect.height * target.lossyScale.y) / 2f;
            var side = fromBelow ? Vector3.down : Vector3.up;
            var centre = target.TransformPoint(target.rect.center);  // hero panels pivot on a corner
            var face = centre + side * (reach + BashGap * unit);
            var hit = centre + side * (reach - BashOverlap * unit);

            var seq = DOTween.Sequence();
            seq.Append(rt.DOMove(face, 0.3f).SetEase(Ease.OutCubic));
            seq.Join(rt.DOScale(rt.localScale * 1.08f, 0.3f).SetEase(Ease.OutCubic));
            seq.Join(rt.DOLocalRotateQuaternion(Quaternion.identity, 0.3f));
            seq.Append(rt.DOMove(face + side * 16f * unit, 0.12f).SetEase(Ease.OutQuad));
            seq.Append(rt.DOMove(hit, 0.09f).SetEase(Ease.InQuad));
            yield return seq.WaitForCompletion();
        }

        /// <summary>
        /// The opponent's cards worth reading before their effects play out: the card they played,
        /// then each of their cards whose ability starts resolving (on either player's action).
        /// Each is held large in the middle for <paramref name="hold"/> seconds, or until a tap.
        /// </summary>
        public IEnumerator Spotlight(GameAction action, float hold)
        {
            var r = action?.result;
            if (r == null || State == null) yield break;
            var shown = new List<int>();
            if (action.type == ActionTypes.Play && action.card.HasValue && action.player != State.human_seat)
                foreach (var m in r.moves)
                    if (m.uid == action.card && m.card_id != null && Defs.TryGetValue(m.card_id, out var def))
                    {
                        shown.Add(m.uid.Value);
                        yield return ShowCard(def, string.Format(UiText.OpponentPlays, OpponentName), hold);
                        break;
                    }
            foreach (int uid in r.abilities)
            {
                var view = CardByUid(uid);
                if (shown.Contains(uid) || !IsOpponentUnit(uid) || view?.Def == null) continue;
                shown.Add(uid);
                yield return ShowCard(view.Def, string.Format(UiText.OpponentAbility, OpponentName), hold);
            }
        }

        IEnumerator ShowCard(CardDef def, string caption, float hold)
        {
            var root = Ui.Stretch("Spotlight", TopLayer, 0, 0, 0, 0);
            var group = root.gameObject.AddComponent<CanvasGroup>();
            Ui.Scrim(root, "Scrim", 0.5f);  // catches the tap, so it doesn't land on the board
            var card = Instantiate(CardPrefab, root);
            card.Bind(def, null);
            card.Input.Handler = null;
            card.Group.blocksRaycasts = false;
            card.Rect.anchorMin = card.Rect.anchorMax = new Vector2(0.5f, 0.5f);
            card.Rect.anchoredPosition = new Vector2(0f, 10f);
            card.Rect.localScale = Vector3.one * SpotlightScale * 0.7f;
            card.Rect.DOScale(SpotlightScale, 0.25f).SetEase(Ease.OutBack);
            float half = CardView.Height * SpotlightScale / 2f;
            Ui.Display(At(root, half + 34f), caption, 24);
            Ui.Body(At(root, -half - 22f), UiText.TapToContinue, 14, Palette.SubtleText, TextAlignmentOptions.Center);
            group.alpha = 0f;
            group.DOFade(1f, 0.15f);

            yield return WaitOrTap(hold);
            group.DOFade(0f, 0.2f).OnComplete(() => Destroy(root.gameObject));
            yield return new WaitForSeconds(0.2f);
        }

        static RectTransform At(RectTransform parent, float y)
        {
            var rt = Ui.Node("Label", parent);
            Ui.Anchor(rt, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0f, 10f + y), new Vector2(600, 36));
            return rt;
        }

        /// <summary>Waits <paramref name="seconds"/>, or less if the player taps or clicks anywhere.</summary>
        public static IEnumerator WaitOrTap(float seconds)
        {
            float end = Time.time + seconds;
            yield return null;  // not the tap that may have started this
            while (Time.time < end && !(Pointer.current?.press.wasPressedThisFrame ?? false))
                yield return null;
        }

        // --- layout

        CardView CardFor(CardInstance c, RectTransform parent)
        {
            if (!_cards.TryGetValue(c.uid, out var view))
            {
                view = Instantiate(CardPrefab, parent);
                view.name = $"Card {c.uid}";
                view.Input.Handler = InputHandler;
                _cards[c.uid] = view;
            }
            else if (view.transform.parent != parent)
            {
                view.transform.SetParent(parent, true);
            }
            if (Defs.TryGetValue(c.card_id, out var def)) view.Bind(def, c);
            else Debug.LogWarning($"Unknown card_id {c.card_id}");
            return view;
        }

        void LayoutRow(RectTransform row, List<CardInstance> units, string zone, HashSet<int> seen, bool animate, int extraSlots)
        {
            int n = units.Count + extraSlots;
            float slot = CardView.Width * FieldScale;
            float width = n * slot + (n - 1) * RowGap;
            float fit = width > MaxRowWidth ? MaxRowWidth / width : 1f;
            for (int i = 0; i < units.Count; i++)
            {
                var c = units[i];
                bool known = _cards.ContainsKey(c.uid);
                var view = CardFor(c, row);
                seen.Add(c.uid);
                if (!known && animate && _spawnAt.TryGetValue(c.uid, out var from))
                {
                    view.Rect.position = from;  // e.g. played from the opponent's hand
                    view.Rect.localScale = Vector3.one * 0.4f;
                }
                var pos = new Vector2((i - (n - 1) / 2f) * (slot + RowGap) * fit, 0f);
                Place(view, pos, Vector3.one * FieldScale * fit, Quaternion.identity, animate);
                view.Rect.SetSiblingIndex(i);
                // Your units that can still do something glow, like playable cards in your hand.
                bool ready = zone == "human_play" && (HasAction(c.uid, ActionTypes.Attack) ||
                    HasAction(c.uid, ActionTypes.AttackHero));
                view.SetMark(ready ? CardMark.Playable : CardMark.None);
                _zoneOf[c.uid] = zone;
            }
            if (extraSlots > 0)
            {
                _ghost.anchoredPosition = new Vector2((n - 1) / 2f * (slot + RowGap) * fit, 0f);
                _ghost.localScale = Vector3.one * fit;
            }
        }

        void LayoutHand(List<CardInstance> hand, HashSet<int> playable, HashSet<int> seen, bool animate)
        {
            int n = hand.Count;
            float step = n > 1 ? Mathf.Min(HandStep, (HandMaxWidth - CardView.Width) / (n - 1)) : 0f;
            for (int i = 0; i < n; i++)
            {
                var c = hand[i];
                bool known = _cards.ContainsKey(c.uid);
                var view = CardFor(c, Hand);
                seen.Add(c.uid);
                // The fan pivots each card on its bottom centre, which sits on a shallow arc; the
                // arc follows x so a big, tightly packed hand doesn't curl off the screen.
                float x = (i - (n - 1) / 2f) * step;
                float u = x / HandStep;
                float angle = -u * 4f;
                var bottom = new Vector2(x, -26f - u * u * 6f);
                float rad = angle * Mathf.Deg2Rad;
                var centre = bottom + new Vector2(-Mathf.Sin(rad), Mathf.Cos(rad)) * (CardView.Height / 2f);
                if (!known && animate && _spawnAt.TryGetValue(c.uid, out var from))
                    view.Rect.position = from;  // drawn: in from your deck
                Place(view, centre, Vector3.one, Quaternion.Euler(0f, 0f, angle), animate);
                view.Rect.SetSiblingIndex(i);
                view.SetMark(playable.Contains(c.uid) ? CardMark.Playable : CardMark.None);
                _zoneOf[c.uid] = "hand";
            }
        }

        static void Place(CardView view, Vector2 pos, Vector3 scale, Quaternion rotation, bool animate)
        {
            var rt = view.Rect;
            rt.DOKill();
            view.SetDimmed(false);
            view.SetTargetRing(TargetRing.None);
            view.SetBadge(null, Color.clear);
            if (!animate)
            {
                rt.anchoredPosition = pos;
                rt.localScale = scale;
                rt.localRotation = rotation;
                return;
            }
            rt.DOAnchorPos(pos, Move).SetEase(Ease.OutCubic);
            rt.DOScale(scale, Move).SetEase(Ease.OutCubic);
            rt.DOLocalRotateQuaternion(rotation, Move).SetEase(Ease.OutCubic);
        }

        bool HasAction(int uid, string type)
        {
            foreach (var a in State.legal_actions)
                if (a.card == uid && a.type == type) return true;
            return false;
        }

        /// <summary>
        /// Plays out an action's result before the new layout: damage and defeats on the cards
        /// involved, hero damage and healing, and cards moving to the discard pile or from a deck
        /// or hidden hand.
        /// </summary>
        void PlayResult(GameAction action, int humanSeat)
        {
            var r = action.result;
            _spawnAt.Clear();
            // Which card did what: pulse each ability's source in order.
            for (int i = 0; i < r.abilities.Count; i++)
            {
                var source = CardByUid(r.abilities[i]);
                if (source != null) DOVirtual.DelayedCall(i * 0.3f, () => { if (source) source.Pulse(); });
            }
            foreach (var d in r.damage)
            {
                var view = CardByUid(d.uid);
                if (view == null || d.amount <= 0) continue;
                FloatText(view.Rect.position, $"−{d.amount}", Palette.Health);
                view.Visual.DOShakeAnchorPos(0.35f, 8f, 20);
            }
            foreach (var h in r.healed)
            {
                var view = CardByUid(h.uid);
                if (view != null) FloatText(view.HealthText.transform.position, $"+{h.amount}", Palette.StatUp);
            }
            foreach (var e in r.effects)
            {
                var view = CardByUid(e.uid);
                if (view != null) FloatEffect(view, e);
            }
            foreach (var p in r.hero_damage)
            {
                if (p.amount <= 0) continue;
                var health = p.player == humanSeat ? HumanHealthText : OpponentHealthText;
                FloatText(health.transform.position, $"−{p.amount}", Palette.Health);
                (p.player == humanSeat ? HumanHero : OpponentHero).DOShakeAnchorPos(0.35f, 8f, 20);
            }
            foreach (var p in r.hero_healed)
                if (p.amount > 0)
                    FloatText((p.player == humanSeat ? HumanHealthText : OpponentHealthText).transform.position,
                        $"+{p.amount}", Palette.StatUp);
            foreach (var p in r.crystals)
                if (p.amount > 0)
                    FloatText((p.player == humanSeat ? HumanManaText : OpponentManaText).transform.position,
                        $"+{p.amount}", Palette.Energy);
            foreach (var m in r.moves)
            {
                bool human = m.player == humanSeat;
                var view = m.uid.HasValue ? CardByUid(m.uid.Value) : null;
                bool played = action.type == ActionTypes.Play && m.uid == action.card;
                if (m.to == Zones.Discard)
                {
                    // An action card resolving, a unit defeated, or a card discarded from a hand.
                    if (played && !human) continue;  // already shown large by Spotlight
                    if (view == null && m.card_id != null && Defs.TryGetValue(m.card_id, out var def))
                        view = ShowOutside(def, OpponentBacks.position);
                    if (view == null) continue;
                    if (played) Leave(view, ShowPlayed);
                    else if (m.from == Zones.Play) Leave(view, Defeat);
                    else Leave(view, Discarded);
                }
                else if (m.from == Zones.Play && m.to == Zones.Hand && !human && view != null)
                {
                    Leave(view, v => FlyInto(v, OpponentBacks));  // returned to a hidden hand
                }
                else if (m.from == Zones.Hand && m.to == Zones.Play && !human && m.uid.HasValue)
                {
                    _spawnAt[m.uid.Value] = OpponentBacks.position;
                }
                else if (m.from == Zones.Deck && m.to == Zones.Hand && human && m.uid.HasValue)
                {
                    _spawnAt[m.uid.Value] = HumanInfoText.transform.position;  // your deck count
                }
            }
        }

        /// <summary>A card the board doesn't hold (the opponent's action or discard), shown from <paramref name="from"/>.</summary>
        CardView ShowOutside(CardDef def, Vector3 from)
        {
            var view = Instantiate(CardPrefab, TopLayer);
            view.Bind(def, null);
            view.Rect.position = from;
            view.Rect.localScale = Vector3.one * 0.4f;
            view.Input.Handler = null;
            return view;
        }

        /// <summary>An action card: shown large in the middle while it resolves, then off to the discard pile.</summary>
        Sequence ShowPlayed(CardView view)
        {
            var seq = DOTween.Sequence();
            seq.Append(view.Rect.DOAnchorPos(new Vector2(0f, 40f), 0.3f).SetEase(Ease.OutCubic));
            seq.Join(view.Rect.DOScale(1.25f, 0.3f));
            seq.Join(view.Rect.DOLocalRotateQuaternion(Quaternion.identity, 0.3f));
            seq.AppendInterval(0.7f);
            seq.Append(view.Group.DOFade(0f, 0.3f));
            seq.Join(view.Rect.DOScale(0.6f, 0.3f));
            return seq;
        }

        static Sequence Discarded(CardView view)
        {
            var seq = DOTween.Sequence();
            seq.Append(view.Rect.DOAnchorPos(view.Rect.anchoredPosition + new Vector2(0f, -60f), 0.4f));
            seq.Join(view.Group.DOFade(0f, 0.4f));
            return seq;
        }

        void FloatEffect(CardView view, EffectRecord e)
        {
            string sign = e.value >= 0 ? "+" : "−";
            switch (e.kind)
            {
                case "stat":
                    var at = e.stat == "power" ? view.PowerText.transform : e.stat == "health" ? view.HealthText.transform : view.Rect;
                    FloatText(at.position, $"{sign}{Mathf.Abs(e.value)}", e.value >= 0 ? Palette.StatUp : Palette.StatDown);
                    break;
                case "keyword":
                    FloatText(view.Rect.position, CardText.KeywordLabel(e.keyword, e.value), Palette.StatUp);
                    break;
                case "freeze":
                    FloatText(view.Rect.position, UiText.Frozen, Palette.Hex("#BDEBFF"));
                    break;
            }
        }

        /// <summary>Takes a card off the board (it's no longer in any zone the board shows) and animates it out.</summary>
        void Leave(CardView view, System.Func<CardView, Sequence> animation)
        {
            _cards.Remove(view.Uid);
            _zoneOf.Remove(view.Uid);
            view.Input.Handler = null;
            view.Rect.DOKill();
            view.transform.SetParent(TopLayer, true);
            animation(view).OnComplete(() => Destroy(view.gameObject));
        }

        static Sequence FlyInto(CardView view, RectTransform target)
        {
            var seq = DOTween.Sequence();
            seq.Append(view.Rect.DOMove(target.position, 0.4f).SetEase(Ease.InCubic));
            seq.Join(view.Rect.DOScale(0.15f, 0.4f).SetEase(Ease.InCubic));
            return seq;
        }

        Sequence Defeat(CardView view)
        {
            FloatText(view.Rect.position + Vector3.up * 30f * Root.lossyScale.y, UiText.Defeated, Palette.Health);
            var seq = DOTween.Sequence();
            seq.Append(view.Visual.DOShakeAnchorPos(0.3f, 10f, 24));
            seq.Append(view.Group.DOFade(0f, 0.35f));
            seq.Join(view.Rect.DOScale(view.Rect.localScale * 0.8f, 0.35f));
            return seq;
        }

        /// <summary>Anything else that left the board (e.g. a mulligan put-back) fades out quietly.</summary>
        void RemoveCardsNotIn(HashSet<int> seen, bool animate)
        {
            var gone = new List<int>();
            foreach (var kv in _cards)
                if (!seen.Contains(kv.Key)) gone.Add(kv.Key);
            foreach (int uid in gone)
            {
                var view = _cards[uid];
                if (!animate)
                {
                    _cards.Remove(uid);
                    _zoneOf.Remove(uid);
                    Destroy(view.gameObject);
                    continue;
                }
                Leave(view, v =>
                {
                    var seq = DOTween.Sequence();
                    seq.Append(v.Group.DOFade(0f, 0.3f));
                    return seq;
                });
            }
        }

        void LayoutBacks(int count)
        {
            while (_backs.Count < count)
            {
                var back = Instantiate(CardBackTemplate, OpponentBacks);
                back.SetActive(true);
                _backs.Add(back);
            }
            // Your hand's fan, mirrored: each back hangs from its top centre on a shallow arc above the screen.
            float step = count > 1 ? Mathf.Min(HandStep, (BackMaxWidth - CardView.Width) / (count - 1)) : 0f;
            for (int i = 0; i < _backs.Count; i++)
            {
                bool shown = i < count;
                _backs[i].SetActive(shown);
                if (!shown) continue;
                float x = (i - (count - 1) / 2f) * step;
                float u = x / HandStep;
                float angle = u * 4f;
                var top = new Vector2(x, CardView.Height - BackVisible + u * u * 6f);
                float rad = angle * Mathf.Deg2Rad;
                var rt = (RectTransform)_backs[i].transform;
                rt.anchoredPosition = top + new Vector2(Mathf.Sin(rad), -Mathf.Cos(rad)) * (CardView.Height / 2f);
                rt.localRotation = Quaternion.Euler(0f, 0f, angle);
            }
        }

        // --- effects

        void FlyCardBack(RectTransform from, RectTransform to)
        {
            var back = Instantiate(CardBackTemplate, TopLayer);
            back.SetActive(true);
            var rt = (RectTransform)back.transform;
            rt.position = from.position;
            var seq = DOTween.Sequence();
            seq.Append(rt.DOMove(to.position, 0.45f).SetEase(Ease.InOutCubic));
            seq.Join(rt.DOScale(0.3f, 0.45f).SetEase(Ease.InCubic));
            seq.OnComplete(() => Destroy(back));
        }

        void FloatText(Vector3 world, string text, Color colour)
        {
            var rt = Ui.Node("Float", TopLayer);
            rt.sizeDelta = new Vector2(200, 40);
            rt.position = world;
            var label = Ui.Display(rt, text, 26);
            label.color = colour;
            var seq = DOTween.Sequence();
            seq.Append(rt.DOAnchorPosY(rt.anchoredPosition.y + 50f, 0.9f).SetEase(Ease.OutCubic));
            seq.Insert(0.5f, DOTween.To(() => label.alpha, x => label.alpha = x, 0f, 0.4f));  // TMP tweens are DOTween Pro only
            seq.OnComplete(() => Destroy(rt.gameObject));
        }

        // --- HUD

        void SetHealth(RectTransform fill, float fullWidth, TMP_Text label, int health, bool animate)
        {
            health = Mathf.Max(health, 0);  // never shown below 0, whatever the server sends
            float t = Mathf.Clamp01(health / (float)HeroHealth);
            var size = new Vector2(fullWidth * t, fill.sizeDelta.y);
            fill.DOKill();
            fill.gameObject.SetActive(t > 0f);
            if (animate) fill.DOSizeDelta(size, 0.5f).SetEase(Ease.OutCubic);
            else fill.sizeDelta = size;
            label.text = health.ToString();
        }

        /// <summary>One crystal per mana crystal: full ones lit, spent ones empty; "mana/crystals" beside them.</summary>
        void SetCrystals(RectTransform crystals, TMP_Text label, PlayerState p)
        {
            var template = crystals.GetChild(0).gameObject;
            while (crystals.childCount < p.crystals)
                Instantiate(template, crystals);
            for (int i = 0; i < crystals.childCount; i++)
            {
                var gem = crystals.GetChild(i);
                gem.gameObject.SetActive(i < p.crystals);
                gem.GetChild(0).gameObject.SetActive(false);
                var crystal = gem.GetChild(1);
                crystal.GetComponent<Image>().sprite = i < p.mana ? ManaFull : ManaEmpty;
                crystal.localScale = Vector3.one;
            }
            label.text = $"{p.mana}/{p.crystals}";
        }
    }
}
