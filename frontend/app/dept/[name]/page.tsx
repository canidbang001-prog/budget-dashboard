import DepartmentPageClient from './DepartmentPageClient';

const ALL_DEPARTMENTS = [
  '가정행복과','갈산면','건설과','건축허가과','결성면','경제정책과',
  '공공시설관리사업소','광천읍','교통과','구항면','금마면','기업지원과',
  '기획감사담당관','농업기술센터','농업정책과','도시과','문화유산과',
  '민원지적과','보건소','복지정책과','산림녹지과','서부면','세무과',
  '수도사업소','안전관리과','은하면','의회사무국','인구전략담당관',
  '자치행정과','장곡면','체육관광과','축산과','해양수산과',
  '혁신전략담당관','홍동면','홍보전산담당관','홍북읍','홍성읍',
  '환경과','회계과',
];

export function generateStaticParams() {
  return ALL_DEPARTMENTS.map((name) => ({ name }));
}

export default async function Page({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return <DepartmentPageClient name={name} />;
}
