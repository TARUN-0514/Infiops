import { PageHeader } from "@/components/page-header";
import { TaskBoard } from "@/components/tasks/task-board";

export default function TasksPage() {
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Tasks" description="Type tasks the way you'd say them. NEXUS works out the date, repeat and project." />
      <TaskBoard />
    </div>
  );
}
