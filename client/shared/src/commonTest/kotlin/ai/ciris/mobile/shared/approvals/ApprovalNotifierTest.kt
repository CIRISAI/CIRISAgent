package ai.ciris.mobile.shared.approvals

import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * New-approval detection and once-only notification.
 *
 * The dedupe contract is the difference between a useful alert and a reason to
 * turn notifications off: the watch polls every 30s, so an approval that
 * notifies on every observation would fire 120 times an hour.
 */
class ApprovalNotifierTest {

    private class FakeSink(
        var permission: Boolean = true,
        var throwOnShow: Boolean = false,
        var throwOnPermission: Boolean = false,
    ) : ApprovalNotificationSink {
        val shown = mutableListOf<Triple<String, String, String>>()

        override fun hasPermission(): Boolean {
            if (throwOnPermission) throw IllegalStateException("platform blew up")
            return permission
        }

        override suspend fun requestPermission(): Boolean = permission

        override fun show(id: String, title: String, body: String) {
            if (throwOnShow) throw IllegalStateException("no notification channel")
            shown += Triple(id, title, body)
        }
    }

    private class ExplodingStore : NotifiedApprovalStore {
        override suspend fun load(): Set<String> = throw IllegalStateException("keychain locked")
        override suspend fun persist(ids: Set<String>) = throw IllegalStateException("keychain locked")
    }

    private fun approval(id: String, budget: RequestedBudget? = null) = PendingApproval(
        id = id,
        kind = if (budget != null) ApprovalKind.TICKET_PROPOSAL else ApprovalKind.DEFERRAL,
        title = "Needs a human: $id",
        detail = "detail",
        createdAt = "2026-07-31T00:00:00Z",
        priority = "normal",
        requestedBy = "agent",
        status = "pending",
        requestedBudget = budget,
    )

    // ─── The core contract ─────────────────────────────────────────────────

    @Test
    fun notifiesOnceForANewApproval() = runTest {
        val sink = FakeSink()
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore())

        val notified = notifier.onApprovalsObserved(listOf(approval("a1")))

        assertEquals(listOf("a1"), notified)
        assertEquals(1, sink.shown.size)
    }

    @Test
    fun doesNotRenotifyOnSubsequentPolls() = runTest {
        val sink = FakeSink()
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore())
        val approvals = listOf(approval("a1"))

        notifier.onApprovalsObserved(approvals)
        notifier.onApprovalsObserved(approvals)
        notifier.onApprovalsObserved(approvals)

        assertEquals(1, sink.shown.size, "one approval must produce exactly one notification")
    }

    @Test
    fun notifiesOnlyTheNewOnesWhenTheListGrows() = runTest {
        val sink = FakeSink()
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore())

        notifier.onApprovalsObserved(listOf(approval("a1")))
        val second = notifier.onApprovalsObserved(listOf(approval("a1"), approval("a2")))

        assertEquals(listOf("a2"), second)
        assertEquals(listOf("a1", "a2"), sink.shown.map { it.first })
    }

    @Test
    fun emptyListNotifiesNothing() = runTest {
        val sink = FakeSink()
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore())

        assertEquals(emptyList(), notifier.onApprovalsObserved(emptyList()))
        assertTrue(sink.shown.isEmpty())
    }

    @Test
    fun previouslyNotifiedIdsSurviveARestart() = runTest {
        val sink = FakeSink()
        // A store pre-loaded as it would be after a restart.
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore(setOf("a1")))

        val notified = notifier.onApprovalsObserved(listOf(approval("a1"), approval("a2")))

        assertEquals(listOf("a2"), notified)
    }

    @Test
    fun forgettingAnIdAllowsItToNotifyAgain() = runTest {
        val sink = FakeSink()
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore())

        notifier.onApprovalsObserved(listOf(approval("a1")))
        notifier.forget("a1")
        notifier.onApprovalsObserved(listOf(approval("a1")))

        assertEquals(2, sink.shown.size)
    }

    // ─── Permission ────────────────────────────────────────────────────────

    @Test
    fun permissionDeniedShowsNothing() = runTest {
        val sink = FakeSink(permission = false)
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore())

        val notified = notifier.onApprovalsObserved(listOf(approval("a1")))

        assertEquals(emptyList(), notified)
        assertTrue(sink.shown.isEmpty())
    }

    @Test
    fun permissionDeniedDoesNotConsumeTheDedupeKey() = runTest {
        // Approvals that arrived while permission was denied must each still
        // fire exactly once if the user later grants it.
        val sink = FakeSink(permission = false)
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore())
        val approvals = listOf(approval("a1"))

        notifier.onApprovalsObserved(approvals)
        sink.permission = true
        val afterGrant = notifier.onApprovalsObserved(approvals)

        assertEquals(listOf("a1"), afterGrant)
        assertEquals(1, sink.shown.size)
    }

    @Test
    fun aPermissionCheckThatThrowsIsTreatedAsDenied() = runTest {
        val sink = FakeSink(throwOnPermission = true)
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore())

        // Must not propagate — a broken platform check cannot be allowed to
        // break the poll loop that also feeds the badge.
        assertEquals(emptyList(), notifier.onApprovalsObserved(listOf(approval("a1"))))
    }

    // ─── Degradation ───────────────────────────────────────────────────────

    @Test
    fun aSinkThatThrowsDoesNotPropagate() = runTest {
        val sink = FakeSink(throwOnShow = true)
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore())

        val notified = notifier.onApprovalsObserved(listOf(approval("a1")))

        // At-most-once: the key is consumed even though delivery failed, so a
        // permanently unavailable channel cannot accumulate a retry backlog.
        assertEquals(listOf("a1"), notified)
        assertEquals(emptyList(), notifier.onApprovalsObserved(listOf(approval("a1"))))
    }

    @Test
    fun aStoreThatThrowsDegradesToInMemoryBehaviourWithoutCrashing() = runTest {
        val sink = FakeSink()
        val notifier = ApprovalNotifier(sink, ExplodingStore())

        val first = notifier.onApprovalsObserved(listOf(approval("a1")))
        val second = notifier.onApprovalsObserved(listOf(approval("a1")))

        assertEquals(listOf("a1"), first)
        // Still deduped within the process even though nothing could be persisted.
        assertEquals(emptyList(), second)
    }

    // ─── Burst collapse ────────────────────────────────────────────────────

    @Test
    fun aBurstCollapsesToASingleSummaryNotification() = runTest {
        val sink = FakeSink()
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore(), burstThreshold = 3)

        val batch = (1..10).map { approval("a$it") }
        val notified = notifier.onApprovalsObserved(batch)

        assertEquals(1, sink.shown.size, "ten new approvals must not be ten notifications")
        assertEquals(ApprovalNotifier.SUMMARY_ID, sink.shown.single().first)
        assertEquals(10, notified.size, "but all ten ids must be marked as notified")
        assertEquals(emptyList(), notifier.onApprovalsObserved(batch))
    }

    @Test
    fun exactlyTheThresholdStillNotifiesIndividually() = runTest {
        val sink = FakeSink()
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore(), burstThreshold = 3)

        notifier.onApprovalsObserved((1..3).map { approval("a$it") })

        assertEquals(3, sink.shown.size)
    }

    @Test
    fun rememberedIdsAreCappedSoTheSetCannotGrowWithoutBound() = runTest {
        val sink = FakeSink()
        val store = InMemoryNotifiedApprovalStore()
        val notifier = ApprovalNotifier(sink, store, maxRemembered = 5, burstThreshold = 100)

        notifier.onApprovalsObserved((1..20).map { approval("a$it") })

        assertEquals(5, store.load().size)
        // Oldest evicted first.
        assertTrue("a20" in store.load())
        assertTrue("a1" !in store.load())
    }

    // ─── Copy ──────────────────────────────────────────────────────────────

    @Test
    fun budgetApprovalsAnnounceTheAmountInTheTitle() = runTest {
        val sink = FakeSink()
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore())

        notifier.onApprovalsObserved(
            listOf(
                approval(
                    "t1",
                    RequestedBudget("25.00", "USDC", "Opt-out fee", null),
                )
            )
        )

        val title = sink.shown.single().second
        assertTrue("25.00" in title, "the operator should see the amount without opening the app")
        assertTrue("USDC" in title)
    }
}
