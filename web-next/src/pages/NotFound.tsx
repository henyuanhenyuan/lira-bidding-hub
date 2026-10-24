import { Link } from "react-router-dom";

import { Empty, PageHead } from "../components/ui";

export default function NotFound() {
  return (
    <>
      <PageHead title="页面不存在" sub="链接可能已失效" />
      <Empty>
        没有找到这个页面。<Link to="/">回到总览</Link>
      </Empty>
    </>
  );
}
